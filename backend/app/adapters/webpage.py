from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from . import AdapterError, FetchedItem, USER_AGENT

MIN_TEXT_LEN = 6  # 过滤「首页」「更多」这类导航噪声


def parse_links(html: str, base_url: str) -> list[FetchedItem]:
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc
    seen: set[str] = set()
    items: list[FetchedItem] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        if len(text) < MIN_TEXT_LEN:
            continue
        absolute = urljoin(base_url, href).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or parsed.netloc != base_host:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        items.append(FetchedItem(title=text[:200], url=absolute))
    return items


def fetch(url: str) -> list[FetchedItem]:
    try:
        resp = httpx.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise AdapterError(f"页面请求失败: {e}") from e
    # 提取到 0 条链接不算错误（spec §10：仅 HTTP 层失败才记 error）
    return parse_links(resp.text, str(resp.url))
