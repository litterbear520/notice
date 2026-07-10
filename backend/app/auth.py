import re
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_session
from .models import LoginCode, User

COOKIE_NAME = "session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 天
CODE_TTL_MINUTES = 10
RESEND_INTERVAL_SECONDS = 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="session")


def sign_session(email: str) -> str:
    return _serializer().dumps(email)


def read_session(token: str) -> str | None:
    try:
        return _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def create_login_code(db: Session, email: str) -> str:
    latest = db.scalars(
        select(LoginCode).where(LoginCode.email == email)
        .order_by(LoginCode.created_at.desc()).limit(1)
    ).first()
    if latest and (datetime.utcnow() - latest.created_at).total_seconds() < RESEND_INTERVAL_SECONDS:
        raise HTTPException(status_code=429, detail="请求过于频繁，请 60 秒后再试")
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(LoginCode(
        email=email, code=code,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
    ))
    db.commit()
    return code


def verify_login_code(db: Session, email: str, code: str) -> bool:
    record = db.scalars(
        select(LoginCode).where(
            LoginCode.email == email, LoginCode.code == code,
            LoginCode.used == False,  # noqa: E712
            LoginCode.expires_at > datetime.utcnow(),
        ).order_by(LoginCode.created_at.desc()).limit(1)
    ).first()
    if not record:
        return False
    record.used = True
    db.commit()
    return True


def get_current_user(request: Request, db: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    email = read_session(token) if token else None
    if not email:
        raise HTTPException(status_code=401, detail="未登录")
    user = db.scalars(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
