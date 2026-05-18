import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.identity.api.dependencies import get_auth_service, get_current_user, get_db
from app.identity.api.schemas import AuthUserResponse, ChangePasswordRequest, LoginRequest, RegisterRequest, UpdateMeRequest
from app.identity.domain.services import AuthService
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException
from app.shared.infrastructure.config import settings
from app.shared.infrastructure.database_tx import transaction
from app.shared.infrastructure.security import revoke_all_user_tokens

# H-03: per-username rate limit in addition to the per-IP limit applied by
# RateLimitMiddleware. An attacker using a distributed IP pool can stay under
# the per-IP cap while still hammering a single account; this closes that gap.
# Applied uniformly regardless of whether the username exists so the limit
# itself cannot be used as an account-enumeration oracle.
_LOGIN_USER_MAX_ATTEMPTS = 5
_LOGIN_USER_WINDOW_SECONDS = 900  # 15 minutes

# M-06: progressive lockout — a 6-hour bucket layered on top of the 5/15min
# bucket. The short bucket still gates each 15-min burst to 5 real guesses,
# but the long bucket caps sustained throughput: after 10 total attempts
# (including rejected ones that still record a hit), the account is locked
# for the remainder of the 6-hour window. Effective cap: ~40 guesses/24h
# vs the previous ~480.
_LOGIN_ESCALATION_MAX_ATTEMPTS = 10
_LOGIN_ESCALATION_WINDOW_SECONDS = 21600  # 6 hours

router = APIRouter(prefix="/api/auth", tags=["auth"])

_REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 3600


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """SEC-C02: deliver tokens via HttpOnly cookies instead of the response body."""
    secure = settings.cookie_secure
    response.set_cookie(
        key="access_token", value=access_token,
        httponly=True, secure=secure, samesite="lax",
        path="/api", max_age=settings.jwt_expire_minutes * 60,
    )
    response.set_cookie(
        key="refresh_token", value=refresh_token,
        httponly=True, secure=secure, samesite="lax",
        path="/api/auth", max_age=_REFRESH_TOKEN_TTL_SECONDS,
    )
    # SEC-03: double-submit CSRF token. Not httpOnly so the SPA can read it
    # via document.cookie and reflect it in the X-CSRF-Token request header.
    # CSRFMiddleware validates that cookie == header on every mutating request.
    # TTL is bound to the access token lifetime so the CSRF token rotates on
    # every /refresh call, limiting the attack window if a token is leaked.
    response.set_cookie(
        key="csrf_token", value=secrets.token_urlsafe(32),
        httponly=False, secure=secure, samesite="lax",
        path="/", max_age=settings.jwt_expire_minutes * 60,
    )


def _clear_auth_cookies(response: Response) -> None:
    secure = settings.cookie_secure
    response.delete_cookie(key="access_token", path="/api", httponly=True, secure=secure, samesite="lax")
    response.delete_cookie(key="refresh_token", path="/api/auth", httponly=True, secure=secure, samesite="lax")
    response.delete_cookie(key="csrf_token", path="/", httponly=False, secure=secure, samesite="lax")


@router.post("/register", status_code=201, summary="使用者註冊", description="建立新帳號，角色可為 parent（家長）或 tutor（家教）。家教註冊時會同步建立 Tutors 資料。", response_model=ApiResponse)
def register(
    body: RegisterRequest,
    conn=Depends(get_db),
    service: AuthService = Depends(get_auth_service),
):
    with transaction(conn):
        user_id = service.register(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
            phone=body.phone,
            email=body.email,
        )
    return ApiResponse(success=True, data={"user_id": user_id}, message="註冊成功")


@router.post("/login", status_code=200, summary="使用者登入", description="驗證帳號密碼後核發 JWT Token，回傳使用者基本資訊。", response_model=ApiResponse[AuthUserResponse])
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    # Account-level bucket is checked before password verification so the cost
    # of bcrypt cannot be used to amplify a distributed brute-force attack.
    # The generic 429 message is identical for existing and unknown usernames
    # to avoid leaking account existence.
    normalized_username = body.username.lower()
    user_bucket = f"login_user|{normalized_username}"
    # M-06: check the longer escalation window first — if the hourly budget
    # is exhausted, the 15-min bucket check is moot.
    escalation_bucket = f"login_escalation|{normalized_username}"
    if not check_and_record_bucket(
        escalation_bucket,
        _LOGIN_ESCALATION_MAX_ATTEMPTS,
        _LOGIN_ESCALATION_WINDOW_SECONDS,
        fail_closed=True,
    ):
        raise HTTPException(
            status_code=429,
            detail="此帳號嘗試次數過多，請稍後再試",
        )
    if not check_and_record_bucket(
        user_bucket,
        _LOGIN_USER_MAX_ATTEMPTS,
        _LOGIN_USER_WINDOW_SECONDS,
        fail_closed=True,
    ):
        raise HTTPException(
            status_code=429,
            detail="此帳號嘗試次數過多，請稍後再試",
        )
    # L-03: forward client context to the audit log. request.client is None
    # for unit-test transports, so guard with a None default.
    source_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    result = service.login(
        username=body.username,
        password=body.password,
        source_ip=source_ip,
        user_agent=user_agent,
    )
    # SEC-C02: tokens delivered via HttpOnly cookies; body carries user info only.
    _set_auth_cookies(response, result["access_token"], result["refresh_token"])
    return ApiResponse(
        success=True,
        data=AuthUserResponse(**result),
    )


@router.post("/refresh", summary="刷新 Token", description="使用 refresh token 取得新的 access token。", response_model=ApiResponse[AuthUserResponse])
def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    # MEDIUM-5: accept the refresh token only from the HttpOnly cookie. The
    # previous body fallback defeated SameSite protection and let a stolen
    # token be replayed from any origin that could POST JSON.
    refresh_token_value = request.cookies.get("refresh_token")
    if not refresh_token_value:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    result = service.refresh(
        refresh_token=refresh_token_value,
        source_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, result["access_token"], result["refresh_token"])
    return ApiResponse(
        success=True,
        data=AuthUserResponse(**result),
    )


@router.post("/logout", summary="登出", description="使目前的 refresh token 失效。", response_model=ApiResponse)
def logout(
    request: Request,
    response: Response,
    user=Depends(get_current_user),
):
    from app.shared.infrastructure.security import decode_refresh_token, invalidate_refresh_token
    # MEDIUM-5: cookie-only (see /refresh note). A stolen refresh token in a
    # body POST would otherwise still be replayable from a cross-origin page.
    refresh_token_value = request.cookies.get("refresh_token")
    if not refresh_token_value:
        raise DomainException("Missing refresh token", status_code=400)
    payload = decode_refresh_token(refresh_token_value)
    # Refuse mismatched / malformed refresh tokens so attackers cannot burn
    # another user's JTI via a forged /logout call.
    if not payload or str(payload.get("sub")) != str(user["sub"]):
        raise DomainException("Invalid refresh token", status_code=400)
    jti = payload.get("jti")
    if not jti:
        raise DomainException("Invalid refresh token", status_code=400)
    invalidate_refresh_token(jti)
    _clear_auth_cookies(response)
    return ApiResponse(success=True, message="已登出")


@router.get("/me", summary="取得個人資訊", description="依據 JWT Token 取得目前登入使用者的資料（不含密碼雜湊）。", response_model=ApiResponse)
def get_me(user=Depends(get_current_user), service: AuthService = Depends(get_auth_service)):
    data = service.get_me(user_id=int(user["sub"]))
    return ApiResponse(success=True, data=data)


@router.put("/me", summary="更新個人資料", description="更新顯示名稱、電話及電子信箱。僅傳入需要變更的欄位。", response_model=ApiResponse)
def update_me(
    body: UpdateMeRequest,
    user=Depends(get_current_user),
    conn=Depends(get_db),
    service: AuthService = Depends(get_auth_service),
):
    fields = body.model_dump(exclude_unset=True)
    with transaction(conn):
        data = service.update_me(user_id=int(user["sub"]), fields=fields)
    return ApiResponse(success=True, data=data)


_PASSWORD_CHANGE_MAX_ATTEMPTS = 5
_PASSWORD_CHANGE_WINDOW_SECONDS = 900  # 15 minutes


@router.put("/password", summary="變更密碼", description="驗證目前密碼後更新為新密碼。", response_model=ApiResponse)
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    user=Depends(get_current_user),
    conn=Depends(get_db),
    service: AuthService = Depends(get_auth_service),
):
    uid = int(user["sub"])
    # M-05: per-user rate limit to prevent current-password brute-forcing
    # via the authenticated change-password endpoint.
    pw_bucket = f"password_change|{uid}"
    if not check_and_record_bucket(
        pw_bucket,
        _PASSWORD_CHANGE_MAX_ATTEMPTS,
        _PASSWORD_CHANGE_WINDOW_SECONDS,
        fail_closed=True,
    ):
        raise HTTPException(
            status_code=429,
            detail="密碼變更嘗試次數過多，請稍後再試",
        )
    with transaction(conn):
        service.change_password(
            user_id=uid,
            current_password=body.current_password,
            new_password=body.new_password,
        )
        # H-01: invalidate all existing refresh tokens so a compromised session
        # cannot survive a user-initiated password change.
        revoke_all_user_tokens(uid, conn=conn)
    # SEC-6: rotate CSRF token on credential change to close the window where
    # a leaked pre-change CSRF token could still authorize requests.
    response.set_cookie(
        key="csrf_token", value=secrets.token_urlsafe(32),
        httponly=False, secure=settings.cookie_secure, samesite="lax",
        path="/", max_age=settings.jwt_expire_minutes * 60,
    )
    return ApiResponse(success=True, message="密碼已更新")
