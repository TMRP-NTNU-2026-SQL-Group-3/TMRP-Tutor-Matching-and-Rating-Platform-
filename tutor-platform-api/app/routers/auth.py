from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_db
from app.exceptions import AppException
from app.models.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.models.common import ApiResponse
from app.repositories.auth_repo import AuthRepository
from app.utils.security import create_access_token, create_refresh_token, decode_refresh_token, hash_password, invalidate_refresh_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", summary="使用者註冊", description="建立新帳號，角色可為 parent（家長）或 tutor（家教）。家教註冊時會同步建立 Tutors 資料。", response_model=ApiResponse)
def register(body: RegisterRequest, conn=Depends(get_db)):
    repo = AuthRepository(conn)

    if repo.find_by_username(body.username):
        raise AppException("帳號已存在")

    if body.role not in ("parent", "tutor"):
        raise AppException("角色必須為 parent 或 tutor")

    hashed = hash_password(body.password)
    user_id = repo.register_user(
        username=body.username,
        password_hash=hashed,
        display_name=body.display_name,
        role=body.role,
        phone=body.phone,
        email=body.email,
    )

    return ApiResponse(success=True, data={"user_id": user_id}, message="註冊成功")


@router.post("/login", summary="使用者登入", description="驗證帳號密碼後核發 JWT Token，回傳使用者基本資訊。", response_model=ApiResponse[TokenResponse])
def login(body: LoginRequest, conn=Depends(get_db)):
    repo = AuthRepository(conn)
    user = repo.find_by_username(body.username)

    if not user or not verify_password(body.password, user["password_hash"]):
        raise AppException("帳號或密碼錯誤")

    token_data = {"sub": str(user["user_id"]), "role": user["role"]}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return ApiResponse(
        success=True,
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user["user_id"],
            role=user["role"],
            display_name=user["display_name"],
        ),
    )


@router.post("/refresh", summary="刷新 Token", description="使用 refresh token 取得新的 access token。", response_model=ApiResponse)
def refresh(body: RefreshRequest, conn=Depends(get_db)):
    payload = decode_refresh_token(body.refresh_token)
    if payload is None:
        raise AppException("刷新令牌無效或已過期", 401)

    # 使舊 refresh token 失效（token rotation）
    if jti := payload.get("jti"):
        invalidate_refresh_token(jti)

    repo = AuthRepository(conn)
    user = repo.find_by_id(int(payload["sub"]))
    if not user:
        raise AppException("使用者不存在", 401)

    token_data = {"sub": str(user["user_id"]), "role": user["role"]}
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)

    return ApiResponse(
        success=True,
        data=TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            user_id=user["user_id"],
            role=user["role"],
            display_name=user["display_name"],
        ),
    )


@router.get("/me", summary="取得個人資訊", description="依據 JWT Token 取得目前登入使用者的資料（不含密碼雜湊）。", response_model=ApiResponse)
def get_me(user=Depends(get_current_user), conn=Depends(get_db)):
    repo = AuthRepository(conn)
    db_user = repo.find_by_id(int(user["sub"]))
    if not db_user:
        raise AppException("使用者不存在")
    db_user.pop("password_hash", None)
    return ApiResponse(success=True, data=db_user)
