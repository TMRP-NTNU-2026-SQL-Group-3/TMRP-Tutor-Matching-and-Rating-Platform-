import re
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(..., description="使用者帳號", examples=["parent01"])
    password: str = Field(..., description="使用者密碼", examples=["P@ssw0rd123"])
    display_name: str = Field(..., description="顯示名稱", examples=["王小明"])
    role: Literal["parent", "tutor"] = Field(..., description="使用者角色（parent 或 tutor）", examples=["parent"])
    phone: str | None = Field(default=None, description="聯絡電話", examples=["0912345678"])
    email: EmailStr | None = Field(default=None, description="電子信箱", examples=["user@example.com"])

    @field_validator("phone", "email", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        # Treat empty strings (default value used by some clients) as missing so the DB
        # stores NULL consistently and unique indexes do not see "" as a duplicate value.
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("密碼長度至少 8 個字元")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密碼須同時包含英文字母與數字")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., description="使用者帳號", examples=["parent01"])
    password: str = Field(..., description="使用者密碼", examples=["P@ssw0rd123"])


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT 存取令牌")
    refresh_token: str = Field(..., description="JWT 刷新令牌")
    token_type: str = Field(default="bearer", description="令牌類型")
    user_id: int = Field(..., description="使用者 ID")
    role: str = Field(..., description="使用者角色")
    display_name: str = Field(..., description="顯示名稱")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="刷新令牌")
