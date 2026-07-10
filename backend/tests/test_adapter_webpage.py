from pathlib import Path

from app.adapters.webpage import parse_links

HTML = (Path(__file__).parent / "fixtures" / "generic_page.html").read_text(encoding="utf-8")
BASE = "https://example.com/notices/index.html"


def test_extracts_valid_links_only():
    items = parse_links(HTML, BASE)
    urls = [i.url for i in items]
    # 保留：站内、有意义文本的链接；相对链接已转绝对；锚点已剥离
    assert "https://example.com/notice/1001" in urls
    assert "https://example.com/notices/detail/1002.html" in urls
    assert "https://example.com/notice/1003" in urls
    # 过滤：短文本导航、# 锚点、javascript:、站外链接
    assert len(items) == 3
    assert all("other-site.com" not in u for u in urls)


def test_titles_come_from_link_text():
    items = parse_links(HTML, BASE)
    assert items[0].title == "某模型服务下线公告（2026-08-01）"


def test_empty_page_returns_empty_list():
    assert parse_links("<html><body>没有链接</body></html>", BASE) == []
