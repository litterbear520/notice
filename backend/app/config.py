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
    # 管理员邮箱，逗号分隔；仅管理员可管理源/关键词与查看成员列表
    admin_emails: str = os.getenv("ADMIN_EMAILS", "970219247@qq.com")
    # 源连续抓取失败达到该轮数时，给管理员发一次告警邮件
    source_alert_failures: int = int(os.getenv("SOURCE_ALERT_FAILURES", "3"))

    @property
    def admin_email_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.admin_emails.split(",") if e.strip())


settings = Settings()
