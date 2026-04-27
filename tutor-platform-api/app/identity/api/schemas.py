import re
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.shared.api.validators import OptionalStr


class RegisterRequest(BaseModel):
    username: str = Field(
        ..., description="使用者帳號", examples=["parent01"],
        min_length=1, max_length=64,
        pattern=r"^[A-Za-z0-9_]([A-Za-z0-9_.\-@]*[A-Za-z0-9_])?$",
    )
    password: str = Field(..., description="使用者密碼", examples=["P@ssw0rd123"])
    display_name: str = Field(..., description="顯示名稱", examples=["王小明"])
    role: Literal["parent", "tutor"] = Field(..., description="使用者角色（parent 或 tutor）", examples=["parent"])
    phone: OptionalStr = Field(default=None, description="聯絡電話", examples=["0912345678"])
    email: EmailStr | None = Field(default=None, description="電子信箱", examples=["user@example.com"])

    # EmailStr cannot share the generic OptionalStr Annotated type, so keep
    # a tiny validator only for that single field.
    @field_validator("email", mode="before")
    @classmethod
    def _email_empty_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        # INFO-1: raised floor to 10 chars to align with 2026 baseline guidance.
        # Per-username login rate limiting (5/15min) remains the primary defence
        # against online guessing; the longer floor adds margin against offline
        # attack on any future hash leak.
        if len(v) < 10:
            raise ValueError("密碼長度至少 10 個字元")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密碼須同時包含英文字母與數字")
        return v


class LoginRequest(BaseModel):
    # LOW-2: cap length and restrict to safe characters so attacker-supplied
    # usernames cannot forge audit-log lines (CRLF injection) or exhaust disk
    # via oversized inputs. The character class matches RegisterRequest norms.
    username: str = Field(
        ..., description="使用者帳號", examples=["parent01"],
        min_length=1, max_length=64,
        pattern=r"^[A-Za-z0-9_]([A-Za-z0-9_.\-@]*[A-Za-z0-9_])?$",
    )
    password: str = Field(..., description="使用者密碼", examples=["P@ssw0rd123"], max_length=128)


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT 存取令牌")
    refresh_token: str = Field(..., description="JWT 刷新令牌")
    token_type: str = Field(default="bearer", description="令牌類型")
    user_id: int = Field(..., description="使用者 ID")
    role: str = Field(..., description="使用者角色")
    display_name: str = Field(..., description="顯示名稱")


class AuthUserResponse(BaseModel):
    """SEC-C02: user info returned in body; tokens are delivered via HttpOnly cookies."""
    user_id: int = Field(..., description="使用者 ID")
    role: str = Field(..., description="使用者角色")
    display_name: str = Field(..., description="顯示名稱")


class UpdateMeRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100, description="顯示名稱")
    phone: OptionalStr = Field(default=None, max_length=20, description="聯絡電話")
    email: EmailStr | None = Field(default=None, description="電子信箱")

    @field_validator("display_name")
    @classmethod
    def _display_name_not_null_when_set(cls, v):
        # Rejects an explicit null so we never attempt to write NULL into
        # users.display_name which is VARCHAR(100) NOT NULL.
        # Pydantic only calls this validator when the field is present in the
        # request body, so omitting display_name entirely (default=None) is fine.
        if v is None:
            raise ValueError("顯示名稱不可設為空")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def _email_empty_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., max_length=128, description="目前密碼")
    new_password: str = Field(..., max_length=128, description="新密碼")

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 10:
            raise ValueError("密碼長度至少 10 個字元")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密碼須同時包含英文字母與數字")
        return v


