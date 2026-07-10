import json

from app.mailer import build_notices_email
from app.models import Notice, Source


def _notice(source, title, url, kws, content="正文内容"):
    return Notice(
        source=source, title=title, url=url, content=content,
        matched=True, matched_keywords=json.dumps(kws, ensure_ascii=False),
    )


def test_single_notice_subject_and_body(db):
    src = Source(name="阿里云公告", type="aliyun_rss", url="http://x")
    n = _notice(src, "百炼模型下线通知", "https://cn.aliyun.com/notice/1", ["模型", "下线"])
    db.add_all([src, n])
    db.commit()
    subject, html = build_notices_email([n])
    assert subject == "【模型公告提醒】阿里云公告: 百炼模型下线通知"
    assert "https://cn.aliyun.com/notice/1" in html
    assert "模型、下线" in html


def test_multi_notice_subject_counts(db):
    src = Source(name="火山引擎产品公告", type="volcengine", url="http://x")
    n1 = _notice(src, "A 公告", "http://a/1", ["模型"])
    n2 = _notice(src, "B 公告", "http://a/2", ["下线"])
    db.add_all([src, n1, n2])
    db.commit()
    subject, html = build_notices_email([n1, n2])
    assert subject == "【模型公告提醒】火山引擎产品公告等 2 条新公告"
    assert "A 公告" in html and "B 公告" in html


def test_excerpt_truncated_to_300(db):
    src = Source(name="S", type="rss", url="http://x")
    n = _notice(src, "T", "http://a/3", [], content="很" * 500)
    db.add_all([src, n])
    db.commit()
    _, html = build_notices_email([n])
    assert "很" * 300 in html
    assert "很" * 301 not in html
