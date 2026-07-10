def find_matches(title: str, content: str, words: list[str]) -> list[str]:
    """忽略大小写的子串匹配，命中任一关键词即算命中（OR 语义）。"""
    text = f"{title}\n{content}".lower()
    return [w for w in words if w.lower() in text]
