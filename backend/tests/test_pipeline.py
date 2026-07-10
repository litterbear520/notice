import json
from datetime import datetime

import pytest
from sqlalchemy import select

from app import pipeline
from app.adapters import AdapterError, FetchedItem
from app.models import Keyword, Notice, Source, User


@pytest.fixture()
def source(db):
    s = Source(name="测试源", type="rss", url="http://feed")
    db.add(s)
    db.add_all([Keyword(word="模型", enabled=True), Keyword(word="下线", enabled=True),
                Keyword(word="停用词", enabled=False)])
    db.commit()
    return s


def _stub_items(monkeypatch, items):
    monkeypatch.setattr(pipeline, "fetch_items", lambda t, u: items)


def test_first_fetch_marks_baseline_and_no_notify(db, source, monkeypatch, sent_emails):
    db.add(User(email="a@qq.com", notify_enabled=True))
    db.commit()
    _stub_items(monkeypatch, [FetchedItem(title="老模型下线公告", url="http://n/1")])
    assert pipeline.fetch_source(db, source) == 1
    assert pipeline.send_pending(db) == 0  # 基线不发
    n = db.scalars(select(Notice)).one()
    assert n.is_baseline and n.matched
    assert json.loads(n.matched_keywords) == ["模型", "下线"]
    assert sent_emails == []
    assert source.last_fetch_status == "ok"


def test_second_fetch_dedupes_and_notifies_matched_only(db, source, monkeypatch, sent_emails):
    db.add_all([User(email="a@qq.com", notify_enabled=True),
                User(email="b@qq.com", notify_enabled=False)])
    db.commit()
    _stub_items(monkeypatch, [FetchedItem(title="旧条目", url="http://n/1")])
    pipeline.fetch_source(db, source)  # 基线
    _stub_items(monkeypatch, [
        FetchedItem(title="旧条目", url="http://n/1"),          # 重复，跳过
        FetchedItem(title="新模型下线通知", url="http://n/2"),   # 命中
        FetchedItem(title="无关价格调整", url="http://n/3"),     # 不命中
    ])
    assert pipeline.fetch_source(db, source) == 2
    assert pipeline.send_pending(db) == 1
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == ["a@qq.com"]  # notify_enabled=False 的不收
    assert "新模型下线通知" in sent_emails[0]["html"]


def test_multiple_pending_merged_into_one_email(db, source, monkeypatch, sent_emails):
    db.add(User(email="a@qq.com", notify_enabled=True))
    db.commit()
    _stub_items(monkeypatch, [FetchedItem(title="基线", url="http://n/0")])
    pipeline.fetch_source(db, source)
    _stub_items(monkeypatch, [FetchedItem(title="模型公告一", url="http://n/1"),
                              FetchedItem(title="模型公告二", url="http://n/2")])
    pipeline.fetch_source(db, source)
    assert pipeline.send_pending(db) == 2
    assert len(sent_emails) == 1  # 合并一封


def test_send_failure_keeps_pending_for_retry(db, source, monkeypatch):
    db.add(User(email="a@qq.com", notify_enabled=True))
    db.commit()
    _stub_items(monkeypatch, [FetchedItem(title="基线", url="http://n/0")])
    pipeline.fetch_source(db, source)
    _stub_items(monkeypatch, [FetchedItem(title="模型下线", url="http://n/1")])
    pipeline.fetch_source(db, source)

    def boom(recipients, subject, html):
        raise RuntimeError("SMTP down")

    monkeypatch.setattr("app.mailer.send_email", boom)
    assert pipeline.send_pending(db) == 0  # 失败，不标记
    n = db.scalars(select(Notice).where(Notice.url == "http://n/1")).one()
    assert n.notified_at is None  # 下一轮重试


def test_adapter_error_records_source_status(db, source, monkeypatch):
    def raise_err(t, u):
        raise AdapterError("网络超时")

    monkeypatch.setattr(pipeline, "fetch_items", raise_err)
    assert pipeline.fetch_source(db, source) == 0
    assert source.last_fetch_status == "error"
    assert "网络超时" in source.last_error


def test_long_url_truncation_consistent(db, source, monkeypatch):
    long_url = "http://n/" + "a" * 1200
    _stub_items(monkeypatch, [FetchedItem(title="超长链接公告", url=long_url)])
    assert pipeline.fetch_source(db, source) == 1
    assert pipeline.fetch_source(db, source) == 0
    notices = list(db.scalars(select(Notice)))
    assert len(notices) == 1
    assert len(notices[0].url) == 1000
    assert source.last_fetch_status == "ok"


def test_run_round_covers_enabled_sources_only(db, monkeypatch, sent_emails):
    s1 = Source(name="启用源", type="rss", url="http://a", enabled=True)
    s2 = Source(name="停用源", type="rss", url="http://b", enabled=False)
    db.add_all([s1, s2, Keyword(word="模型", enabled=True)])
    db.commit()
    called = []
    monkeypatch.setattr(pipeline, "fetch_items", lambda t, u: called.append(u) or [])
    result = pipeline.run_round(db)
    assert called == ["http://a"]
    assert result == {"sources": 1, "new_items": 0, "notified": 0}
