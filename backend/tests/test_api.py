import json

from sqlalchemy import select

from app.models import Keyword, LoginCode, Notice, Source


def _login(client, db, email="admin@qq.com"):
    client.post("/api/auth/request-code", json={"email": email})
    code = db.scalars(select(LoginCode).where(LoginCode.email == email)).first().code
    client.post("/api/auth/verify", json={"email": email, "code": code})


def _seed(db):
    src = Source(name="阿里云公告", type="aliyun_rss", url="http://a", is_builtin=True)
    db.add(src)
    db.commit()
    db.add_all([
        Notice(source_id=src.id, title="模型下线通知", url="http://n/1", content="正文A",
               matched=True, matched_keywords=json.dumps(["模型", "下线"], ensure_ascii=False)),
        Notice(source_id=src.id, title="价格调整公告", url="http://n/2", content="正文B",
               matched=False, matched_keywords="[]"),
    ])
    db.commit()
    return src


def test_notices_default_matched_only(client, db):
    _seed(db)
    data = client.get("/api/notices").json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["title"] == "模型下线通知"
    assert item["source_name"] == "阿里云公告"
    assert item["matched_keywords"] == ["模型", "下线"]


def test_notices_all_and_search(client, db):
    _seed(db)
    assert client.get("/api/notices?matched_only=false").json()["total"] == 2
    assert client.get("/api/notices?matched_only=false&q=价格").json()["total"] == 1


def test_sources_list_public(client, db):
    _seed(db)
    data = client.get("/api/sources").json()
    assert data[0]["name"] == "阿里云公告" and data[0]["is_builtin"] is True


def test_create_source_requires_login(client, db):
    body = {"name": "自定义", "type": "rss", "url": "https://x.com/feed.xml"}
    assert client.post("/api/sources", json=body).status_code == 401
    _login(client, db)
    resp = client.post("/api/sources", json=body)
    assert resp.status_code == 201
    assert resp.json()["is_builtin"] is False


def test_create_source_validates_type_and_url(client, db):
    _login(client, db)
    assert client.post("/api/sources", json={"name": "x", "type": "volcengine", "url": "https://x.com"}).status_code == 422
    assert client.post("/api/sources", json={"name": "x", "type": "rss", "url": "ftp://x.com"}).status_code == 422


def test_patch_and_delete_source(client, db):
    src = _seed(db)
    _login(client, db)
    assert client.patch(f"/api/sources/{src.id}", json={"enabled": False}).json()["enabled"] is False
    # 内置源不可删除
    assert client.delete(f"/api/sources/{src.id}").status_code == 400
    custom = client.post("/api/sources", json={"name": "c", "type": "rss", "url": "https://c.com/f"}).json()
    assert client.delete(f"/api/sources/{custom['id']}").status_code == 204


def test_manual_fetch(client, db, monkeypatch, sent_emails):
    src = _seed(db)
    _login(client, db)
    from app.adapters import FetchedItem
    from app import pipeline

    monkeypatch.setattr(pipeline, "fetch_items",
                        lambda t, u: [FetchedItem(title="新模型下线", url="http://n/9")])
    db.add(Keyword(word="下线", enabled=True))
    db.commit()
    resp = client.post(f"/api/sources/{src.id}/fetch")
    assert resp.status_code == 200
    assert resp.json()["new_items"] == 1


def test_keywords_crud(client, db):
    assert client.get("/api/keywords").json() == []
    assert client.post("/api/keywords", json={"word": "下线"}).status_code == 401
    _login(client, db)
    created = client.post("/api/keywords", json={"word": "下线"})
    assert created.status_code == 201
    assert client.post("/api/keywords", json={"word": "下线"}).status_code == 409
    kid = created.json()["id"]
    assert client.patch(f"/api/keywords/{kid}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"/api/keywords/{kid}").status_code == 204
