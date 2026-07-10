from datetime import datetime

import feedparser
import httpx
from bs4 import BeautifulSoup

from . import AdapterError, FetchedItem, USER_AGENT


def parse_feed(content: bytes) -> list[FetchedItem]:
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise AdapterError(f"RSS 解析失败: {feed.bozo_exception}")
    items: list[FetchedItem] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        raw = ""
        if entry.get("content"):
            raw = entry.content[0].get("value", "")
        elif entry.get("summary"):
            raw = entry.summary
        text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)[:5000]
        published = None
        if entry.get("published_parsed"):
            published = datetime(*entry.published_parsed[:6])  # feedparser 已转 UTC
        items.append(FetchedItem(title=title, url=link, content=text, published_at=published))
    return items


def fetch(url: str) -> list[FetchedItem]:
    try:
        resp = httpx.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise AdapterError(f"RSS 请求失败: {e}") from e
    return parse_feed(resp.content)
