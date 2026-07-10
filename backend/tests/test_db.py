import importlib

from sqlalchemy import select

from app.models import Keyword, Source


def _fresh_db_module(tmp_path, monkeypatch, name):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/{name}.db")
    import app.config as config_module

    importlib.reload(config_module)
    import app.db as db_module

    importlib.reload(db_module)
    return db_module


def test_init_db_creates_tables_and_seeds(tmp_path, monkeypatch):
    db_module = _fresh_db_module(tmp_path, monkeypatch, "t1")
    db_module.init_db()
    with db_module.SessionLocal() as s:
        sources = s.scalars(select(Source)).all()
        keywords = s.scalars(select(Keyword)).all()
    assert {x.type for x in sources} == {"aliyun_rss", "volcengine"}
    assert all(x.is_builtin for x in sources)
    assert "下线" in {k.word for k in keywords}


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    db_module = _fresh_db_module(tmp_path, monkeypatch, "t2")
    db_module.init_db()
    db_module.init_db()
    with db_module.SessionLocal() as s:
        assert len(s.scalars(select(Source)).all()) == 2
