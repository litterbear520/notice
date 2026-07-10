import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.qq.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "465"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_auth_code: str = os.getenv("SMTP_AUTH_CODE", "")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    fetch_interval_minutes: int = int(os.getenv("FETCH_INTERVAL_MINUTES", "30"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/notice.db")
    enable_scheduler: bool = os.getenv("ENABLE_SCHEDULER", "1") == "1"


settings = Settings()
