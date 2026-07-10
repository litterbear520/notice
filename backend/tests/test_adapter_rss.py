from datetime import datetime
from pathlib import Path

from app.adapters.rss import parse_feed

FIXTURE = (Path(__file__).parent / "fixtures" / "aliyun_rss.xml").read_bytes()


def test_parse_feed_extracts_items():
    items = parse_feed(FIXTURE)
    assert len(items) == 2
    first = items[0]
    assert first.title == "【大模型服务平台百炼】部分老旧模型下线通知"
    assert first.url == "https://cn.aliyun.com/notice/118331"
    assert "qwen-flash-us" in first.content
    assert "<p>" not in first.content  # HTML 已剥离
    # pubDate +0800 转为 UTC：10:00+08:00 -> 02:00 UTC
    assert first.published_at == datetime(2026, 7, 8, 2, 0, 0)


def test_parse_feed_invalid_xml_raises():
    import pytest

    from app.adapters import AdapterError

    with pytest.raises(AdapterError):
        parse_feed(b"this is not xml at all")
