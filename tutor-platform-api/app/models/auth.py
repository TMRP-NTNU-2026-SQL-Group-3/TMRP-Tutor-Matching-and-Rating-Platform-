from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., description="使用者帳號", examples=["parent01"])
    password: str = Field(..., description="使用者密碼", examples=["P@ssw0rd123"])
    display_name: str = Field(..., description="顯示名稱", examples=["王小明"])
    role: str = Field(..., description="使用者角色（parent 或 tutor）", examples=["parent"])
    phone: str | None = Field(default=None, description="聯絡電話", examples=["0912345678"])
    email: str | None = Field(default=None, description="電子信箱", examples=["user@example.com"])


class LoginRequest(BaseModel):
    username: str = Field(..., description="使用者帳號", examples=["parent01"])
    password: str = Field(..., description="使用者密碼", examples=["P@ssw0rd123"])


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT 存取令牌", examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."])
    token_type: str = Field(default="bearer", description="令牌類型", examples=["bearer"])
    user_id: int = Field(..., description="使用者 ID", examples=[1])
    role: str = Field(..., description="使用者角色", examples=["parent"])
    display_name: str = Field(..., description="顯示名稱", examples=["王小明"])
