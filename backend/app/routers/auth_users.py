import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, mailer
from ..db import get_session
from ..models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class RequestCodeBody(BaseModel):
    email: str


class VerifyBody(BaseModel):
    email: str
    code: str


class MePatch(BaseModel):
    notify_enabled: bool


@router.post("/auth/request-code")
def request_code(body: RequestCodeBody, db: Session = Depends(get_session)):
    email = body.email.strip().lower()
    if not auth.EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="邮箱格式不正确")
    code = auth.create_login_code(db, email)
    try:
        mailer.send_login_code(email, code)
    except Exception:
        logger.exception("验证码邮件发送失败")
        raise HTTPException(status_code=502, detail="验证码邮件发送失败，请检查 SMTP 配置")
    return {"message": "验证码已发送"}


@router.post("/auth/verify")
def verify(body: VerifyBody, response: Response, db: Session = Depends(get_session)):
    email = body.email.strip().lower()
    if not auth.verify_login_code(db, email, body.code.strip()):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    user = db.scalars(select(User).where(User.email == email)).first()
    if not user:
        user = User(email=email)
        db.add(user)
    user.last_login_at = datetime.utcnow()
    db.commit()
    response.set_cookie(
        auth.COOKIE_NAME, auth.sign_session(email),
        max_age=auth.SESSION_MAX_AGE, httponly=True, samesite="lax",
    )
    return {"email": email}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME)
    return {"message": "已退出"}


@router.get("/me")
def me(user: User = Depends(auth.get_current_user)):
    return {"email": user.email, "notify_enabled": user.notify_enabled}


@router.patch("/me")
def update_me(
    body: MePatch,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_session),
):
    user.notify_enabled = body.notify_enabled
    db.commit()
    return {"email": user.email, "notify_enabled": user.notify_enabled}


@router.get("/users")
def list_users(
    user: User = Depends(auth.get_current_user), db: Session = Depends(get_session)
):
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return [
        {"email": u.email, "notify_enabled": u.notify_enabled, "last_login_at": u.last_login_at}
        for u in users
    ]
