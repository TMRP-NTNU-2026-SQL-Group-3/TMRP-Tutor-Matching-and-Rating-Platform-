from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str  # "parent" | "tutor"
    phone: str | None = None
    email: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    display_name: str
