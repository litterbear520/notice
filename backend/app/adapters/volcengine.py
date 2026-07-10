import json
import re
from datetime import datetime, timezone

import httpx

from . import AdapterError, FetchedItem, USER_AGENT

LIBRARY_ID = 82379
ANNOUNCE_ROOT_DOC_ID = "1159176"  # 「产品公告」目录节点
# 三个原地更新的主公告文档：模型下线公告 / 模型发布公告 / 产品更新公告
WATCH_DOC_IDS = ["1350667", "1159178", "1159177"]

_ROUTER_DATA_RE = re.compile(r"window\._ROUTER_DATA = (\{.*?\})\s*</script>", re.S)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)  # 统一 naive UTC
    except ValueError:
        return None


def parse_doc_page(html: str, doc_id: str) -> tuple[FetchedItem | None, dict | None]:
    m = _ROUTER_DATA_RE.search(html)
    if not m:
        raise AdapterError(f"文档 {doc_id} 页面中未找到 _ROUTER_DATA（站点可能已改版）")
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


def fetch(url: str) -> list[FetchedItem]:
    items: list[FetchedItem] = []
    doc_list_map: dict | None = None
    errors: list[str] = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
    ) as client:
        for doc_id in WATCH_DOC_IDS:
            try:
                resp = client.get(
                    f"https://docs.volcengine.com/docs/{LIBRARY_ID}/{doc_id}",
                    params={"lang": "zh"},
                )
                resp.raise_for_status()
                item, dlm = parse_doc_page(resp.text, doc_id)
            except (httpx.HTTPError, AdapterError) as e:
                errors.append(f"{doc_id}: {e}")
                continue
            if item:
                items.append(item)
            if doc_list_map is None:
                doc_list_map = dlm
    if not items:
        raise AdapterError("火山引擎监控文档全部抓取失败: " + "; ".join(errors))
    items.extend(_new_doc_items(doc_list_map))
    return items
