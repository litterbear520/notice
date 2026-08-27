from datetime import datetime
from pathlib import Path

import httpx
import pytest

from app.adapters import AdapterError
from app.adapters import volcengine
from app.adapters.volcengine import (
    _new_api_doc_items,
    _new_doc_items,
    parse_doc_detail,
    parse_doc_page,
)

HTML = (Path(__file__).parent / "fixtures" / "volcengine.html").read_text(encoding="utf-8")

API_DETAIL = {
    "Result": {
        "DocumentID": 1350667,
        "Title": "模型下线公告",
        "UpdatedTime": "2026-07-17T07:49:11Z",
        "MDContent": "最新一批模型下线安排",
    }
}

API_DOC_LIST = {
    "Result": {
        "970": [
            {"DocumentID": 1159176, "ParentID": 0, "Title": "产品公告"},
            {"DocumentID": 1159177, "ParentID": 1159176, "Title": "产品更新公告"},
            {"DocumentID": 1159178, "ParentID": 1159176, "Title": "模型发布公告"},
            {"DocumentID": 1350667, "ParentID": 1159176, "Title": "模型下线公告"},
            {"DocumentID": 1456326, "ParentID": 1159176, "Title": "历史公告"},
            {"DocumentID": 1600000, "ParentID": 1456326, "Title": "历史模型下线公告"},
            {"DocumentID": 9999999, "ParentID": 0, "Title": "购买指南（非公告，不应出现）"},
        ]
    }
}


def test_parse_doc_detail_builds_update_item():
    item = parse_doc_detail(API_DETAIL, "1350667")
    assert item.title == "模型下线公告 已更新"
    assert item.url == "https://www.volcengine.com/docs/82379/1350667#u20260717074911"
    assert item.content == "最新一批模型下线安排"
    assert item.published_at == datetime(2026, 7, 17, 7, 49, 11)


def test_new_api_doc_items_covers_announcement_subtree_only():
    items = _new_api_doc_items(API_DOC_LIST)
    titles = {item.title for item in items}
    assert "模型下线公告" in titles
    assert "历史模型下线公告" in titles
    assert "购买指南（非公告，不应出现）" not in titles
    assert all(item.url.startswith("https://www.volcengine.com/docs/82379/") for item in items)


def test_fetch_uses_official_api_without_requesting_ssr(monkeypatch):
    calls: list[str] = []

    def fake_get(self, url, params=None):
        calls.append(url)
        if url == volcengine.DOC_DETAIL_API:
            doc_id = str(params["DocumentID"])
            payload = {
                "Result": {
                    "DocumentID": int(doc_id),
                    "Title": "监控公告 " + doc_id,
                    "UpdatedTime": "2026-07-17T07:49:11Z",
                    "MDContent": "模型下线安排",
                }
            }
        elif url == volcengine.DOC_LIST_API:
            payload = API_DOC_LIST
        else:
            pytest.fail(f"不应请求 SSR 页面: {url}")
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    items = volcengine.fetch("https://docs.volcengine.com/docs/82379/1159176?lang=zh")
    updated = [item for item in items if item.title.endswith("已更新")]
    assert len(updated) == len(volcengine.WATCH_DOC_IDS)
    assert calls.count(volcengine.DOC_DETAIL_API) == len(volcengine.WATCH_DOC_IDS)
    assert calls.count(volcengine.DOC_LIST_API) == 1


def test_parse_doc_page_builds_update_item():
    item, doc_list_map = parse_doc_page(HTML, "1350667")
    assert item is not None
    assert item.title == "模型下线公告 已更新"
    # 合成锚点 = 文档URL + #u + UpdatedTime 压缩时间戳，更新时间不变则 URL 不变（去重跳过）
    assert item.url == "https://www.volcengine.com/docs/82379/1350667#u20260708034649"
    assert "doubao-pro-4k" in item.content
    assert item.published_at == datetime(2026, 7, 8, 3, 46, 49)
    assert doc_list_map is not None


def test_same_updated_time_produces_same_url():
    item1, _ = parse_doc_page(HTML, "1350667")
    item2, _ = parse_doc_page(HTML, "1350667")
    assert item1.url == item2.url


def test_new_doc_items_covers_announcement_subtree_only():
    _, doc_list_map = parse_doc_page(HTML, "1350667")
    items = _new_doc_items(doc_list_map)
    titles = {i.title for i in items}
    # 产品公告子树下的所有后代文档（不含根节点本身）
    assert "模型下线公告" in titles
    assert "历史公告" in titles
    assert "26年春节期间访问方式调整公告" in titles
    # 非公告子树的文档不能进来
    assert "购买指南（非公告，不应出现）" not in titles
    # URL 使用 www.volcengine.com 文档地址
    assert all(i.url.startswith("https://www.volcengine.com/docs/82379/") for i in items)


def test_missing_router_data_raises():
    with pytest.raises(AdapterError):
        parse_doc_page("<html><body>改版了</body></html>", "1350667")


# 站点 SSR 故障时会以 HTTP 200 返回不含 _ROUTER_DATA 的错误壳页面
ERROR_SHELL = '<!doctype html><html><head><!-- 错误码css --></head><body></body></html>'


def test_fetch_retries_transient_error_page(monkeypatch):
    page_calls: list[str] = []

    def fake_get(self, url, params=None):
        if url in {volcengine.DOC_DETAIL_API, volcengine.DOC_LIST_API}:
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("API 暂时不可用", request=request)
        page_calls.append(url)
        # 第一个文档前两次命中降级错误页，第三次及之后返回正常页面
        text = ERROR_SHELL if len(page_calls) <= 2 else HTML
        return httpx.Response(200, text=text, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(volcengine.time, "sleep", lambda s: None)

    items = volcengine.fetch("https://docs.volcengine.com/docs/82379/1159176?lang=zh")
    updated = [i for i in items if i.title.endswith("已更新")]
    # 官方 API 全部失败后回退 SSR，三个文档都应成功（第一个靠重试）。
    assert len(updated) == len(volcengine.WATCH_DOC_IDS)
