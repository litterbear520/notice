import os

os.environ["ENABLE_SCHEDULER"] = "0"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_EMAILS"] = "admin@qq.com"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """限流器是进程级内存状态，测试间必须清空。"""
    from app import auth

    auth.email_code_limiter.reset()
    auth.global_code_limiter.reset()
    auth.verify_limiter.reset()
    yield


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture()
def sent_emails(monkeypatch):
    """截获所有外发邮件。pipeline/auth 必须通过 `from . import mailer` + `mailer.send_email(...)` 调用。"""
    sent = []

    def fake_send(recipients, subject, html):
        sent.append({"to": list(recipients), "subject": subject, "html": html})

    monkeypatch.setattr("app.mailer.send_email", fake_send)
    return sent


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import app

    def override():
        yield db

    app.dependency_overrides[get_session] = override
    # 不用 with（避免触发 lifespan 里的 init_db/scheduler），直接请求即可
    yield TestClient(app)
    app.dependency_overrides.clear()
