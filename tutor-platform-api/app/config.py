from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 資料庫
    access_db_path: str = "data/tutoring.accdb"

    # JWT 認證
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15  # access token 短效期（搭配 refresh token）

    # Super Admin 帳號（系統啟動時自動建立）
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # 評價鎖定天數（超過此天數的評價不可再修改）
    review_lock_days: int = 7

    # huey 任務佇列
    huey_db_path: str = "data/huey.db"

    # 日誌
    log_file: str = "logs/app.log"
    log_level: str = "INFO"
    log_format: str = "json"

    # CORS
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def validate_security_defaults(self):
        if self.jwt_secret_key == "change-me-in-production":
            raise ValueError(
                "JWT_SECRET_KEY 必須在 .env 中設定安全的密鑰，不可使用預設值。"
                "請執行: python -c \"import secrets; print(secrets.token_hex(32))\" 生成密鑰。"
            )
        if self.admin_password == "admin123":
            raise ValueError(
                "ADMIN_PASSWORD 必須在 .env 中設定強密碼，不可使用預設值 'admin123'。"
            )
        return self


settings = Settings()
