from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.identity.api.dependencies import get_auth_service, get_current_user, get_db
from app.identity.api.schemas import AuthUserResponse, LoginRequest, RegisterRequest
from app.identity.domain.services import AuthService
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException
from app.shared.infrastructure.config import settings
from app.shared.infrastructure.database_tx import transaction

# H-03: per-username rate limit in addition to the per-IP limit applied by
# RateLimitMiddleware. An attacker using a distributed IP pool can stay under
# the per-IP cap while still hammering a single account; this closes that gap.
# Applied uniformly regardless of whether the username exists so the limit
# itself cannot be used as an account-enumeration oracle.
_LOGIN_USER_MAX_ATTEMPTS = 5
_LOGIN_USER_WINDOW_SECONDS = 900  # 15 minutes

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


def _clear_auth_cookies(response: Response) -> None:
    secure = settings.cookie_secure
    response.delete_cookie(key="access_token", path="/api", httponly=True, secure=secure, samesite="lax")
    response.delete_cookie(key="refresh_token", path="/api/auth", httponly=True, secure=secure, samesite="lax")


@router.post("/register", summary="使用者註冊", description="建立新帳號，角色可為 parent（家長）或 tutor（家教）。家教註冊時會同步建立 Tutors 資料。", response_model=ApiResponse)
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


@router.post("/login", summary="使用者登入", description="驗證帳號密碼後核發 JWT Token，回傳使用者基本資訊。", response_model=ApiResponse[AuthUserResponse])
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
    user_bucket = f"login_user|{body.username.lower()}"
    # M-06: sensitive — fail closed if the rate-limit DB is unreachable,
    # so a counter outage cannot remove the per-account brake that defends
    # against distributed-IP credential stuffing.
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
    result = service.refresh(refresh_token=refresh_token_value)
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
