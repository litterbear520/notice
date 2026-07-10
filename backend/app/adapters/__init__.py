from dataclasses import dataclass
from datetime import datetime


class AdapterError(Exception):
    """源抓取/解析失败，携带面向人的错误描述。"""


@dataclass
class FetchedItem:
    title: str
    url: str
    content: str = ""
    published_at: datetime | None = None


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def fetch_items(source_type: str, url: str) -> list[FetchedItem]:
    from . import rss, volcengine, webpage

    if source_type in ("rss", "aliyun_rss"):
        return rss.fetch(url)
    if source_type == "webpage":
        return webpage.fetch(url)
    if source_type == "volcengine":
        return volcengine.fetch(url)
    raise AdapterError(f"未知源类型: {source_type}")
