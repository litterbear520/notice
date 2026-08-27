import json
import logging
import re
import time
from datetime import datetime, timezone

import httpx

from . import AdapterError, FetchedItem, USER_AGENT

logger = logging.getLogger(__name__)

LIBRARY_ID = 82379
ANNOUNCE_ROOT_DOC_ID = "1159176"  # 「产品公告」目录节点
# 三个原地更新的主公告文档：模型下线公告 / 模型发布公告 / 产品更新公告
WATCH_DOC_IDS = ["1350667", "1159178", "1159177"]
DOC_DETAIL_API = "https://docs.volcengine.com/api/doc/getDocDetail"
DOC_LIST_API = "https://docs.volcengine.com/api/doc/getDocList"
# 站点 SSR 间歇性故障时会以 HTTP 200 返回不含 _ROUTER_DATA 的错误壳页面，需重试
# 旧 SSR 解析仅作为官方文档 API 全部失败时的回退路径。
MAX_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 1.0

_ROUTER_DATA_RE = re.compile(r"window\._ROUTER_DATA = (\{.*?\})\s*</script>", re.S)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)  # 统一 naive UTC
    except ValueError:
        return None


def parse_doc_detail(data: dict, doc_id: str) -> FetchedItem:
    """把官方文档详情 API 响应转换为一个可按更新时间去重的条目。"""
    result = data.get("Result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise AdapterError(f"文档 {doc_id} 详情 API 响应缺少 Result")
    if str(result.get("DocumentID", "")) != str(doc_id):
        raise AdapterError(f"文档 {doc_id} 详情 API 返回了错误的 DocumentID")
    title = result.get("Title")
    updated = _parse_time(result.get("UpdatedTime", ""))
    content = result.get("MDContent") or result.get("Content") or ""
    if not title or not updated or not content:
        raise AdapterError(f"文档 {doc_id} 详情 API 响应缺少标题、更新时间或正文")
    stamp = updated.strftime("%Y%m%d%H%M%S")
    return FetchedItem(
        title=f"{title} 已更新",
        url=f"https://www.volcengine.com/docs/{LIBRARY_ID}/{doc_id}#u{stamp}",
        content=content[:5000],
        published_at=updated,
    )


def parse_doc_page(html: str, doc_id: str) -> tuple[FetchedItem | None, dict | None]:
    m = _ROUTER_DATA_RE.search(html)
    if not m:
        raise AdapterError(
            f"文档 {doc_id} 页面中未找到 _ROUTER_DATA（站点临时故障或已改版）"
        )
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise AdapterError(f"文档 {doc_id} 的 _ROUTER_DATA 解析失败: {e}") from e
    loader = data.get("loaderData") or {}
    doc_list_map = (loader.get("docs/(libid)/layout") or {}).get("docListMap")
    cur = (loader.get("docs/(libid)/(docid$)/page") or {}).get("curDoc") or {}
    item = None
    updated = _parse_time(cur.get("UpdatedTime", ""))
    if cur.get("Title") and updated:
        stamp = updated.strftime("%Y%m%d%H%M%S")
        item = FetchedItem(
            title=f"{cur['Title']} 已更新",
            url=f"https://www.volcengine.com/docs/{LIBRARY_ID}/{doc_id}#u{stamp}",
            content=(cur.get("MDContent") or "")[:5000],
            published_at=updated,
        )
    return item, doc_list_map


def _new_doc_items(doc_list_map: dict | None) -> list[FetchedItem]:
    if not doc_list_map:
        return []
    titles: dict[str, str] = {}
    children: dict[str, list[str]] = {}
    for group in doc_list_map.values():
        if not isinstance(group, dict):
            continue
        for doc_id, node in group.items():
            if not isinstance(node, dict):
                continue
            value = node.get("value") or {}
            if value.get("Title"):
                titles[str(doc_id)] = value["Title"]
            children[str(doc_id)] = [str(c) for c in (node.get("children") or [])]
    result: list[FetchedItem] = []
    queue, visited = [ANNOUNCE_ROOT_DOC_ID], set()
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        queue.extend(children.get(current, []))
        if current == ANNOUNCE_ROOT_DOC_ID:
            continue
        title = titles.get(current)
        if title:
            result.append(FetchedItem(
                title=title,
                url=f"https://www.volcengine.com/docs/{LIBRARY_ID}/{current}",
            ))
    return result


def _new_api_doc_items(data: dict) -> list[FetchedItem]:
    """从官方目录 API 的扁平 ParentID 结构中提取产品公告子树。"""
    groups = data.get("Result") if isinstance(data, dict) else None
    if not isinstance(groups, dict):
        raise AdapterError("火山引擎目录 API 响应缺少 Result")
    nodes: dict[str, dict] = {}
    children: dict[str, list[str]] = {}
    for group in groups.values():
        if not isinstance(group, list):
            continue
        for node in group:
            if not isinstance(node, dict) or node.get("DocumentID") is None:
                continue
            doc_id = str(node["DocumentID"])
            parent_id = str(node.get("ParentID", ""))
            nodes[doc_id] = node
            children.setdefault(parent_id, []).append(doc_id)
    if ANNOUNCE_ROOT_DOC_ID not in nodes:
        raise AdapterError("火山引擎目录 API 中未找到产品公告根节点")
    result: list[FetchedItem] = []
    queue, visited = [ANNOUNCE_ROOT_DOC_ID], set()
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        queue.extend(children.get(current, []))
        if current == ANNOUNCE_ROOT_DOC_ID:
            continue
        title = nodes.get(current, {}).get("Title")
        if title:
            result.append(FetchedItem(
                title=title,
                url=f"https://www.volcengine.com/docs/{LIBRARY_ID}/{current}",
            ))
    return result


def _request_json(client: httpx.Client, url: str, params: dict, label: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(RETRY_DELAY_SECONDS * attempt)
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise AdapterError(f"{label}返回的不是 JSON 对象")
            return data
        except (httpx.HTTPError, ValueError, AdapterError) as e:
            last_error = e
    raise AdapterError(f"{label}重试 {MAX_ATTEMPTS} 次仍失败: {last_error}")


def _fetch_from_api(client: httpx.Client) -> list[FetchedItem]:
    items: list[FetchedItem] = []
    errors: list[str] = []
    for doc_id in WATCH_DOC_IDS:
        try:
            data = _request_json(
                client,
                DOC_DETAIL_API,
                {
                    "LibraryID": str(LIBRARY_ID),
                    "DocumentID": doc_id,
                    "AuditDocumentID": "",
                    "type": "online",
                },
                f"文档 {doc_id} 详情 API ",
            )
            items.append(parse_doc_detail(data, doc_id))
        except AdapterError as e:
            errors.append(str(e))
    try:
        doc_list = _request_json(
            client,
            DOC_LIST_API,
            {
                "LibraryID": str(LIBRARY_ID),
                "DataSchema": "all_second_nav",
                "type": "online",
            },
            "目录 API ",
        )
        items.extend(_new_api_doc_items(doc_list))
    except AdapterError as e:
        errors.append(str(e))
    updated_items = [item for item in items if item.title.endswith("已更新")]
    if not updated_items:
        raise AdapterError("火山引擎监控文档 API 全部抓取失败: " + "; ".join(errors))
    if errors:
        logger.warning("火山引擎 API 部分抓取失败: %s", "; ".join(errors))
    return items


def _fetch_from_ssr(client: httpx.Client) -> list[FetchedItem]:
    """兼容旧页面：仅在官方文档 API 完全不可用时调用。"""
    items: list[FetchedItem] = []
    doc_list_map: dict | None = None
    errors: list[str] = []
    for doc_id in WATCH_DOC_IDS:
        item = dlm = None
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
            try:
                resp = client.get(
                    f"https://docs.volcengine.com/docs/{LIBRARY_ID}/{doc_id}",
                    params={"lang": "zh"},
                )
                resp.raise_for_status()
                item, dlm = parse_doc_page(resp.text, doc_id)
                last_error = None
                break
            except (httpx.HTTPError, AdapterError) as e:
                last_error = e
        if last_error is not None:
            errors.append(f"{doc_id}: 重试 {MAX_ATTEMPTS} 次仍失败: {last_error}")
            continue
        if item:
            items.append(item)
        if doc_list_map is None:
            doc_list_map = dlm
    if not items:
        raise AdapterError("火山引擎监控文档 SSR 全部抓取失败: " + "; ".join(errors))
    if errors:
        logger.warning("火山引擎 SSR 部分文档抓取失败: %s", "; ".join(errors))
    items.extend(_new_doc_items(doc_list_map))
    return items


def fetch(url: str) -> list[FetchedItem]:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
    ) as client:
        try:
            return _fetch_from_api(client)
        except AdapterError as api_error:
            logger.warning("火山引擎官方 API 不可用，回退 SSR: %s", api_error)
            try:
                return _fetch_from_ssr(client)
            except AdapterError as ssr_error:
                raise AdapterError(
                    f"火山引擎官方 API 与 SSR 均抓取失败: API: {api_error}; SSR: {ssr_error}"
                ) from ssr_error
