from fastapi import APIRouter, Depends

from app.database_tx import transaction
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

    if body.role not in ("parent", "tutor"):
        raise AppException("角色必須為 parent 或 tutor")

    hashed = hash_password(body.password)

    # BUG-FIX: 將帳號重複檢查與 INSERT 包入同一交易，防止並發註冊時
    # 兩個請求同時通過檢查，其中一個因 UNIQUE 約束產生 500 錯誤。
    # 外層 try/except 作為最終安全網：即使在 MS Access 弱隔離下
    # 兩個交易同時通過檢查，UNIQUE 約束仍會攔截，轉為友善的 400 回應。
    try:
        with transaction(conn):
            if repo.find_by_username(body.username):
                raise AppException("帳號已存在")

            user_id = repo.register_user(
                username=body.username,
                password_hash=hashed,
                display_name=body.display_name,
                role=body.role,
                phone=body.phone,
                email=body.email,
            )
    except AppException:
        raise
    except Exception:
        # UNIQUE 約束衝突（並發註冊相同帳號），轉為友善錯誤訊息
        if repo.find_by_username(body.username):
            raise AppException("帳號已存在")
        raise

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


@router.post("/logout", summary="登出", description="使目前的 refresh token 失效。", response_model=ApiResponse)
def logout(body: RefreshRequest, user=Depends(get_current_user)):
    payload = decode_refresh_token(body.refresh_token)
    if payload and (jti := payload.get("jti")):
        invalidate_refresh_token(jti)
    return ApiResponse(success=True, message="已登出")


@router.get("/me", summary="取得個人資訊", description="依據 JWT Token 取得目前登入使用者的資料（不含密碼雜湊）。", response_model=ApiResponse)
def get_me(user=Depends(get_current_user), conn=Depends(get_db)):
    repo = AuthRepository(conn)
    db_user = repo.find_by_id(int(user["sub"]))
    if not db_user:
        raise AppException("使用者不存在")
    db_user.pop("password_hash", None)
    return ApiResponse(success=True, data=db_user)
