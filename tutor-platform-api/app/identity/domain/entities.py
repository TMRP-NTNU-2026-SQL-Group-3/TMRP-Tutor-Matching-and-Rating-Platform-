from dataclasses import dataclass


@dataclass
class User:
    user_id: int
    username: str
    password_hash: str
    role: str           # "parent" | "tutor" | "admin"
    display_name: str
    phone: str | None = None
    email: str | None = None
