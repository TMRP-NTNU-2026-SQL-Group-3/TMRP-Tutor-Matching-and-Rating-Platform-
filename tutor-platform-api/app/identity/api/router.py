from fastapi import APIRouter, Depends

from app.identity.api.dependencies import get_auth_service, get_current_user, get_db
from app.identity.api.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.identity.domain.services import AuthService
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException
from app.shared.infrastructure.database_tx import transaction

router = APIRouter(prefix="/api/auth", tags=["auth"])


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


@router.post("/login", summary="使用者登入", description="驗證帳號密碼後核發 JWT Token，回傳使用者基本資訊。", response_model=ApiResponse[TokenResponse])
def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    result = service.login(username=body.username, password=body.password)
    return ApiResponse(
        success=True,
        data=TokenResponse(**result),
    )


@router.post("/refresh", summary="刷新 Token", description="使用 refresh token 取得新的 access token。", response_model=ApiResponse)
def refresh(body: RefreshRequest, service: AuthService = Depends(get_auth_service)):
    result = service.refresh(refresh_token=body.refresh_token)
    return ApiResponse(
        success=True,
        data=TokenResponse(**result),
    )


@router.post("/logout", summary="登出", description="使目前的 refresh token 失效。", response_model=ApiResponse)
def logout(body: RefreshRequest, user=Depends(get_current_user)):
    from app.shared.infrastructure.security import decode_refresh_token, invalidate_refresh_token
    payload = decode_refresh_token(body.refresh_token)
    # Refuse mismatched / malformed refresh tokens so attackers cannot burn
    # another user's JTI via a forged /logout call.
    if not payload or str(payload.get("sub")) != str(user["sub"]):
        raise DomainException("Invalid refresh token", status_code=400)
    jti = payload.get("jti")
    if not jti:
        raise DomainException("Invalid refresh token", status_code=400)
    invalidate_refresh_token(jti)
    return ApiResponse(success=True, message="已登出")


@router.get("/me", summary="取得個人資訊", description="依據 JWT Token 取得目前登入使用者的資料（不含密碼雜湊）。", response_model=ApiResponse)
def get_me(user=Depends(get_current_user), service: AuthService = Depends(get_auth_service)):
    data = service.get_me(user_id=int(user["sub"]))
    return ApiResponse(success=True, data=data)
