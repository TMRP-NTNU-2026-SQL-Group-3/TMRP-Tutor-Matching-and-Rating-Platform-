from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_db
from app.exceptions import AppException
from app.models.auth import LoginRequest, RegisterRequest, TokenResponse
from app.models.common import ApiResponse
from app.repositories.auth_repo import AuthRepository
from app.utils.security import create_access_token, hash_password, verify_password

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

    token = create_access_token(
        {"sub": str(user["user_id"]), "role": user["role"]}
    )

    return ApiResponse(
        success=True,
        data=TokenResponse(
            access_token=token,
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
