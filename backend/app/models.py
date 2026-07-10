from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))  # aliyun_rss / volcengine / rss / webpage
    url: Mapped[str] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_fetch_status: Mapped[str | None] = mapped_column(String(10), default=None)  # ok / error
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    notices: Mapped[list["Notice"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (UniqueConstraint("source_id", "url", name="uq_notice_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    content: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_keywords: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组字符串
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped["Source"] = relationship(back_populates="notices")


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(100), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class LoginCode(Base):
    __tablename__ = "login_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
