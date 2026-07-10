from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import LoginCode, User


def _request_code(client, email="user@qq.com"):
    return client.post("/api/auth/request-code", json={"email": email})


def _login(client, db, email="user@qq.com"):
    _request_code(client, email)
    code = db.scalars(select(LoginCode).where(LoginCode.email == email)).first().code
    return client.post("/api/auth/verify", json={"email": email, "code": code})


def test_request_code_sends_email(client, db, sent_emails):
    resp = _request_code(client)
    assert resp.status_code == 200
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == ["user@qq.com"]
    code = db.scalars(select(LoginCode)).one()
    assert len(code.code) == 6 and code.code in sent_emails[0]["html"]


def test_request_code_invalid_email(client, sent_emails):
    assert _request_code(client, "not-an-email").status_code == 422
    assert sent_emails == []


def test_request_code_rate_limited_60s(client, db, sent_emails):
    assert _request_code(client).status_code == 200
    assert _request_code(client).status_code == 429
    assert len(sent_emails) == 1


def test_verify_creates_user_and_sets_cookie(client, db, sent_emails):
    resp = _login(client, db)
    assert resp.status_code == 200
    assert "session" in resp.cookies
    user = db.scalars(select(User)).one()
    assert user.email == "user@qq.com" and user.notify_enabled


def test_verify_wrong_code(client, db, sent_emails):
    _request_code(client)
    resp = client.post("/api/auth/verify", json={"email": "user@qq.com", "code": "000000"})
    assert resp.status_code == 400


def test_code_single_use(client, db, sent_emails):
    _request_code(client)
    code = db.scalars(select(LoginCode)).one().code
    assert client.post("/api/auth/verify", json={"email": "user@qq.com", "code": code}).status_code == 200
    assert client.post("/api/auth/verify", json={"email": "user@qq.com", "code": code}).status_code == 400


def test_expired_code_rejected(client, db, sent_emails):
    _request_code(client)
    record = db.scalars(select(LoginCode)).one()
    record.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    resp = client.post("/api/auth/verify", json={"email": "user@qq.com", "code": record.code})
    assert resp.status_code == 400


def test_me_requires_login(client):
    assert client.get("/api/me").status_code == 401


def test_me_and_notify_toggle(client, db, sent_emails):
    _login(client, db)
    assert client.get("/api/me").json() == {"email": "user@qq.com", "notify_enabled": True}
    resp = client.patch("/api/me", json={"notify_enabled": False})
    assert resp.json()["notify_enabled"] is False


def test_users_list_requires_login_and_lists_members(client, db, sent_emails):
    assert client.get("/api/users").status_code == 401
    _login(client, db)
    users = client.get("/api/users").json()
    assert [u["email"] for u in users] == ["user@qq.com"]


def test_logout_clears_cookie(client, db, sent_emails):
    _login(client, db)
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401
