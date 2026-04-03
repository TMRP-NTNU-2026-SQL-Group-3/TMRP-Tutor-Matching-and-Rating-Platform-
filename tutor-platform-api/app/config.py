from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 資料庫
    access_db_path: str = "data/tutoring.accdb"

    # JWT 認證
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

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

    # CORS
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
