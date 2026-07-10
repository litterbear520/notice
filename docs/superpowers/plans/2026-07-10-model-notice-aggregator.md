# 模型公告聚合与邮件提醒平台 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 聚合各厂商模型上下线公告（内置阿里云 RSS + 火山引擎，支持自定义 RSS/网页源），关键词筛选后立即通过 QQ 邮箱 SMTP 群发提醒，并提供 Next.js 网页端（公告时间线、源管理、关键词管理、邮箱验证码登录）。

**Architecture:** 单体 FastAPI 后端（进程内 APScheduler 定时抓取 + REST API + smtplib 发信），SQLite 单文件存储，Next.js 前端通过 rewrites 把 `/api/*` 代理到后端（同源化，HttpOnly Cookie 直接生效）。适配器模式支持四种源类型；抓取→去重→关键词筛选→合并通知的流水线天然幂等（发送失败下一轮自动重试）。

**Tech Stack:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 / APScheduler 3.x / feedparser / httpx / BeautifulSoup4 / itsdangerous / pytest；Next.js 14 (App Router) + React 18 + TypeScript；Docker Compose。

**Spec:** `docs/superpowers/specs/2026-07-10-model-notice-aggregator-design.md`（已确认，实现遇到与本计划不一致处以 spec 为准）

## Global Constraints

- Python 3.11+；SQLAlchemy 2.0 风格（`Mapped` / `mapped_column`）；所有时间统一存**naive UTC**（`datetime.utcnow()`）。
- 敏感配置只走环境变量：`SMTP_HOST`（默认 `smtp.qq.com`）、`SMTP_PORT`（默认 `465`）、`SMTP_USER`、`SMTP_AUTH_CODE`、`SECRET_KEY`、`FETCH_INTERVAL_MINUTES`（默认 `30`）、`DATABASE_URL`（默认 `sqlite:///./data/notice.db`）、`ENABLE_SCHEDULER`（默认 `1`，测试设 `0`）。
- 后端端口 8000，前端端口 3000；前端所有请求走相对路径 `/api/*`（由 Next.js rewrites 代理），**前端代码中不得出现后端绝对地址**。
- UI 文案全部使用简体中文。
- notices 表 `(source_id, url)` 唯一；正文截断 5000 字符；邮件摘要 300 字符。
- 内置源（`is_builtin=true`）不可删除，仅可停用。
- 新源首次抓取全部标记 `is_baseline=true`，不发邮件。
- 每个任务完成即 commit；提交信息用中文，格式 `feat|test|chore: 描述`。
- 后端测试命令统一为在 `backend/` 目录下运行 `python -m pytest tests -v`（Windows 也一样）。
- 前端不写单测（spec 决策），每个前端任务以 `npm run build` 通过 + 手动验收点为准。

## 文件结构总览

```
notice/
├── backend/
│   ├── app/
│   │   ├── __init__.py          # 空文件
│   │   ├── config.py            # 环境变量 Settings（含 .env 加载）
│   │   ├── models.py            # 5 张表的 ORM 模型
│   │   ├── db.py                # engine/SessionLocal/init_db（建表+种子）/get_session
│   │   ├── matching.py          # 关键词匹配
│   │   ├── adapters/
│   │   │   ├── __init__.py      # FetchedItem / AdapterError / fetch_items 分发
│   │   │   ├── rss.py           # rss + aliyun_rss（同一实现）
│   │   │   ├── webpage.py       # 通用网页链接提取（差异检测的提取端）
│   │   │   └── volcengine.py    # _ROUTER_DATA 解析：更新检测 + 新文档检测
│   │   ├── mailer.py            # smtplib 发送 + 通知邮件/验证码邮件构建
│   │   ├── pipeline.py          # fetch_source / send_pending / run_round
│   │   ├── auth.py              # 验证码生成校验、token 签发、get_current_user
│   │   ├── scheduler.py         # APScheduler BackgroundScheduler
│   │   ├── main.py              # FastAPI app 组装 + lifespan
│   │   └── routers/
│   │       ├── __init__.py      # 空文件
│   │       ├── notices.py
│   │       ├── sources.py
│   │       ├── keywords.py
│   │       └── auth_users.py    # auth + me + users
│   ├── tests/
│   │   ├── conftest.py          # 内存 SQLite fixture + client fixture + sent_emails
│   │   ├── fixtures/            # aliyun_rss.xml / volcengine.html / generic_page.html
│   │   ├── test_matching.py
│   │   ├── test_adapter_rss.py
│   │   ├── test_adapter_webpage.py
│   │   ├── test_adapter_volcengine.py
│   │   ├── test_mailer.py
│   │   ├── test_pipeline.py
│   │   ├── test_auth.py
│   │   └── test_api.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── layout.tsx / globals.css / page.tsx（时间线）
│   │   ├── components/NavBar.tsx
│   │   ├── sources/page.tsx
│   │   ├── keywords/page.tsx
│   │   ├── login/page.tsx
│   │   └── settings/page.tsx
│   ├── lib/api.ts               # fetch 封装 + 类型定义
│   ├── next.config.js           # rewrites 代理 /api → 后端
│   ├── package.json / tsconfig.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── .gitignore
```

**关键接口约定（跨任务使用，签名必须一致）：**

- `app.adapters.FetchedItem`：`@dataclass`，字段 `title: str`、`url: str`、`content: str = ""`、`published_at: datetime | None = None`
- `app.adapters.fetch_items(source_type: str, url: str) -> list[FetchedItem]`，失败抛 `app.adapters.AdapterError`
- `app.matching.find_matches(title: str, content: str, words: list[str]) -> list[str]`
- `app.mailer.send_email(recipients: list[str], subject: str, html: str) -> None`（测试中被 monkeypatch 的唯一出口）
- `app.pipeline.fetch_source(db, source) -> int`、`app.pipeline.send_pending(db) -> int`、`app.pipeline.run_round(db) -> dict`
- `app.auth.get_current_user`（FastAPI 依赖，Cookie 名 `session`，未登录 401）
- `app.db.get_session`（FastAPI 依赖，测试中被 override）

---

### Task 1: 后端脚手架、配置与数据层

**Files:**
- Create: `.gitignore`、`backend/requirements.txt`、`backend/app/__init__.py`、`backend/app/config.py`、`backend/app/models.py`、`backend/app/db.py`
- Test: `backend/tests/conftest.py`、`backend/tests/test_db.py`

**Interfaces:**
- Produces: `app.config.settings`（属性见代码）；`app.models` 的 `Base/Source/Notice/Keyword/User/LoginCode`；`app.db` 的 `engine/SessionLocal/init_db()/get_session()`、`DEFAULT_KEYWORDS`、`BUILTIN_SOURCES`
- Consumes: 无（首个任务）

- [ ] **Step 1: 创建 .gitignore 与 Python 环境**

`.gitignore`（仓库根目录）：

```gitignore
# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/

# 数据与密钥
data/
.env

# Node
node_modules/
.next/
frontend/out/
```

`backend/requirements.txt`：

```
fastapi>=0.110
uvicorn[standard]>=0.29
sqlalchemy>=2.0
apscheduler>=3.10,<4
feedparser>=6.0
httpx>=0.27
beautifulsoup4>=4.12
itsdangerous>=2.1
python-dotenv>=1.0
pytest>=8.0
```

创建虚拟环境并安装（在仓库根目录执行）：

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows；Linux/Mac 用 .venv/bin/pip
```

后续所有 `python`/`pytest` 命令均指该 venv 中的解释器（Windows: `.venv/Scripts/python`）。

- [ ] **Step 2: 写配置模块**

`backend/app/__init__.py`：空文件。

`backend/app/config.py`：

```python
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.qq.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "465"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_auth_code: str = os.getenv("SMTP_AUTH_CODE", "")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    fetch_interval_minutes: int = int(os.getenv("FETCH_INTERVAL_MINUTES", "30"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/notice.db")
    enable_scheduler: bool = os.getenv("ENABLE_SCHEDULER", "1") == "1"


settings = Settings()
```

- [ ] **Step 3: 写 ORM 模型**

`backend/app/models.py`：

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))  # aliyun_rss / volcengine / rss / webpage
    url: Mapped[str] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_fetch_status: Mapped[str | None] = mapped_column(String(10), default=None)  # ok / error
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    notices: Mapped[list["Notice"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (UniqueConstraint("source_id", "url", name="uq_notice_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    content: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_keywords: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组字符串
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped["Source"] = relationship(back_populates="notices")


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(100), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class LoginCode(Base):
    __tablename__ = "login_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 4: 写测试 conftest 和 db 初始化的失败测试**

`backend/tests/conftest.py`：

```python
import os

os.environ["ENABLE_SCHEDULER"] = "0"
os.environ["SECRET_KEY"] = "test-secret"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture()
def sent_emails(monkeypatch):
    """截获所有外发邮件。pipeline/auth 必须通过 `from . import mailer` + `mailer.send_email(...)` 调用。"""
    sent = []

    def fake_send(recipients, subject, html):
        sent.append({"to": list(recipients), "subject": subject, "html": html})

    monkeypatch.setattr("app.mailer.send_email", fake_send)
    return sent
```

`backend/tests/test_db.py`（用「设环境变量 → reload config 和 db 模块」的方式让每个测试拿到指向独立临时库的全新 engine）：

```python
import importlib

from sqlalchemy import select

from app.models import Keyword, Source


def _fresh_db_module(tmp_path, monkeypatch, name):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/{name}.db")
    import app.config as config_module

    importlib.reload(config_module)
    import app.db as db_module

    importlib.reload(db_module)
    return db_module


def test_init_db_creates_tables_and_seeds(tmp_path, monkeypatch):
    db_module = _fresh_db_module(tmp_path, monkeypatch, "t1")
    db_module.init_db()
    with db_module.SessionLocal() as s:
        sources = s.scalars(select(Source)).all()
        keywords = s.scalars(select(Keyword)).all()
    assert {x.type for x in sources} == {"aliyun_rss", "volcengine"}
    assert all(x.is_builtin for x in sources)
    assert "下线" in {k.word for k in keywords}


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    db_module = _fresh_db_module(tmp_path, monkeypatch, "t2")
    db_module.init_db()
    db_module.init_db()
    with db_module.SessionLocal() as s:
        assert len(s.scalars(select(Source)).all()) == 2
```

- [ ] **Step 5: 运行测试确认失败**

Run: `cd backend && python -m pytest tests -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.db'`）

- [ ] **Step 6: 实现 db.py**

`backend/app/db.py`：

```python
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from .config import settings
from .models import Base, Keyword, Source

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

DEFAULT_KEYWORDS = [
    "模型", "下线", "停售", "停止服务", "废弃", "到期",
    "百炼", "qwen", "豆包", "doubao", "deprecat",
]

BUILTIN_SOURCES = [
    {"name": "阿里云公告", "type": "aliyun_rss",
     "url": "https://cn.aliyun.com/rss/notice/zh.xml"},
    {"name": "火山引擎产品公告", "type": "volcengine",
     "url": "https://docs.volcengine.com/docs/82379/1159176?lang=zh"},
]


def init_db() -> None:
    if settings.database_url.startswith("sqlite:///"):
        path = settings.database_url.removeprefix("sqlite:///")
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalars(select(Source).limit(1)).first():
            for item in BUILTIN_SOURCES:
                db.add(Source(**item, is_builtin=True))
        if not db.scalars(select(Keyword).limit(1)).first():
            for word in DEFAULT_KEYWORDS:
                db.add(Keyword(word=word, enabled=True))
        db.commit()


def get_session():
    with SessionLocal() as db:
        yield db
```

- [ ] **Step 7: 运行测试确认通过**

Run: `cd backend && python -m pytest tests -v`
Expected: PASS（2 个测试）

- [ ] **Step 8: Commit**

```bash
git add .gitignore backend/
git commit -m "feat: 后端脚手架——配置、ORM 模型与数据库初始化（含内置源与默认关键词种子）"
```

---

### Task 2: 关键词匹配

**Files:**
- Create: `backend/app/matching.py`
- Test: `backend/tests/test_matching.py`

**Interfaces:**
- Produces: `find_matches(title: str, content: str, words: list[str]) -> list[str]`（返回命中的关键词原文列表，忽略大小写，OR 语义）
- Consumes: 无

- [ ] **Step 1: 写失败测试**

`backend/tests/test_matching.py`：

```python
from app.matching import find_matches


def test_matches_in_title():
    assert find_matches("部分老旧模型下线通知", "", ["模型", "下线", "qwen"]) == ["模型", "下线"]


def test_matches_in_content_case_insensitive():
    assert find_matches("公告", "Qwen-Max is DEPRECATED", ["qwen", "deprecat"]) == ["qwen", "deprecat"]


def test_no_match_returns_empty():
    assert find_matches("数据库价格调整", "RDS 优惠", ["模型", "下线"]) == []


def test_empty_keywords():
    assert find_matches("模型下线", "内容", []) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_matching.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

`backend/app/matching.py`：

```python
def find_matches(title: str, content: str, words: list[str]) -> list[str]:
    """忽略大小写的子串匹配，命中任一关键词即算命中（OR 语义）。"""
    text = f"{title}\n{content}".lower()
    return [w for w in words if w.lower() in text]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_matching.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 5: Commit**

```bash
git add backend/app/matching.py backend/tests/test_matching.py
git commit -m "feat: 关键词匹配（忽略大小写子串、OR 语义）"
```

---

### Task 3: RSS 适配器（rss / aliyun_rss）

**Files:**
- Create: `backend/app/adapters/__init__.py`、`backend/app/adapters/rss.py`、`backend/tests/fixtures/aliyun_rss.xml`
- Test: `backend/tests/test_adapter_rss.py`

**Interfaces:**
- Produces: `app.adapters` 的 `FetchedItem`、`AdapterError`、`USER_AGENT`、`fetch_items(source_type, url)`；`app.adapters.rss` 的 `parse_feed(content: bytes) -> list[FetchedItem]` 与 `fetch(url: str) -> list[FetchedItem]`
- Consumes: 无

- [ ] **Step 1: 写测试 fixture**

`backend/tests/fixtures/aliyun_rss.xml`（模拟阿里云真实结构：`content:encoded` + `pubDate`）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>阿里云公告</title>
    <link>https://cn.aliyun.com/notice</link>
    <item>
      <title>【大模型服务平台百炼】部分老旧模型下线通知</title>
      <link>https://cn.aliyun.com/notice/118331</link>
      <pubDate>Wed, 08 Jul 2026 10:00:00 +0800</pubDate>
      <content:encoded><![CDATA[<p>尊敬的用户，<b>qwen-flash-us</b> 等模型将于 2026-10-10 下线，请迁移至 qwen3.7-plus。</p>]]></content:encoded>
    </item>
    <item>
      <title>【云数据库RDS】价格调整公告</title>
      <link>https://cn.aliyun.com/notice/118332</link>
      <pubDate>Tue, 07 Jul 2026 09:00:00 +0800</pubDate>
      <content:encoded><![CDATA[<p>RDS 部分规格价格调整。</p>]]></content:encoded>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: 写失败测试**

`backend/tests/test_adapter_rss.py`：

```python
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
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_adapter_rss.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 4: 实现适配器公共模块和 RSS 解析**

`backend/app/adapters/__init__.py`：

```python
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
```

`backend/app/adapters/rss.py`：

```python
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
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_adapter_rss.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters/ backend/tests/
git commit -m "feat: RSS 适配器（阿里云公告与通用 RSS/Atom 共用）"
```

---

### Task 4: 通用网页链接提取适配器（webpage）

**Files:**
- Create: `backend/app/adapters/webpage.py`、`backend/tests/fixtures/generic_page.html`
- Test: `backend/tests/test_adapter_webpage.py`

**Interfaces:**
- Produces: `app.adapters.webpage` 的 `parse_links(html: str, base_url: str) -> list[FetchedItem]` 与 `fetch(url) -> list[FetchedItem]`。「差异检测」的"差异"部分由 pipeline 的 (source_id, url) 去重完成，适配器只负责提取当前页面全部有效链接。
- Consumes: Task 3 的 `FetchedItem`、`AdapterError`、`USER_AGENT`

- [ ] **Step 1: 写测试 fixture**

`backend/tests/fixtures/generic_page.html`：

```html
<html>
<body>
  <nav>
    <a href="/">首页</a>
    <a href="#top">回到顶部</a>
    <a href="javascript:void(0)">展开</a>
  </nav>
  <ul class="notice-list">
    <li><a href="/notice/1001">某模型服务下线公告（2026-08-01）</a></li>
    <li><a href="detail/1002.html">平台维护升级通知公告</a></li>
    <li><a href="https://example.com/notice/1003#section">新模型上线发布公告</a></li>
    <li><a href="https://other-site.com/x">友情链接站外公告页面</a></li>
  </ul>
</body>
</html>
```

- [ ] **Step 2: 写失败测试**

`backend/tests/test_adapter_webpage.py`：

```python
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
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_adapter_webpage.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 4: 实现**

`backend/app/adapters/webpage.py`：

```python
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
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_adapter_webpage.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters/webpage.py backend/tests/
git commit -m "feat: 通用网页链接提取适配器（链接差异检测的提取端）"
```

---

### Task 5: 火山引擎适配器（volcengine）

**Files:**
- Create: `backend/app/adapters/volcengine.py`、`backend/tests/fixtures/volcengine.html`
- Test: `backend/tests/test_adapter_volcengine.py`

**Interfaces:**
- Produces: `app.adapters.volcengine` 的 `parse_doc_page(html: str, doc_id: str) -> tuple[FetchedItem | None, dict | None]`、`_new_doc_items(doc_list_map: dict | None) -> list[FetchedItem]`、`fetch(url) -> list[FetchedItem]`
- Consumes: Task 3 的 `FetchedItem`、`AdapterError`、`USER_AGENT`

**背景（已实测验证，2026-07-10）：** 火山文档页静态 HTML 内嵌 `window._ROUTER_DATA = {...}</script>`，其中 `loaderData["docs/(libid)/(docid$)/page"].curDoc` 含 `Title`、`DocumentID`、`UpdatedTime`（ISO 8601，如 `2026-07-08T03:46:49Z`）、`MDContent`（Markdown 纯文本正文）；`loaderData["docs/(libid)/layout"].docListMap` 是 `{组ID: {文档ID: {value: {Title}, children: [子文档ID]}}}` 结构的文档树，「产品公告」目录节点 docId=`1159176`，children 覆盖全部公告文档（含历史归档）。公告是**单文档原地追加更新**，所以用 UpdatedTime 做更新检测（url 加 `#u<时间戳>` 合成锚点利用唯一键去重）。

- [ ] **Step 1: 写测试 fixture**

`backend/tests/fixtures/volcengine.html`（按实测结构缩小的合成样本）：

```html
<html><head><title>模型下线公告--火山方舟</title></head><body>
<div id="root"></div>
<script>window._SSR_DATA = {"ok":true}</script>
<script>window._ROUTER_DATA = {"loaderData":{"docs/(libid)/layout":{"docListMap":{"970":{"0":{"children":[1159176]},"1159176":{"value":{"Title":"产品公告"},"children":[1159177,1159178,1350667,1456326]},"1159177":{"value":{"Title":"产品更新公告"},"children":[]},"1159178":{"value":{"Title":"模型发布公告"},"children":[]},"1350667":{"value":{"Title":"模型下线公告"},"children":[]},"1456326":{"value":{"Title":"历史公告"},"children":[2277241]},"2277241":{"value":{"Title":"2026 公告"},"children":[2191792]},"2191792":{"value":{"Title":"26年春节期间访问方式调整公告"},"children":[]},"9999":{"value":{"Title":"购买指南（非公告，不应出现）"},"children":[]}}}},"docs/(libid)/(docid$)/page":{"curDoc":{"DocumentID":1350667,"Title":"模型下线公告","UpdatedTime":"2026-07-08T03:46:49Z","MDContent":"# 第九批模型下线说明\n\n模型 doubao-pro-4k 将于 2026-09-21 14:00 下线（EOS），请迁移至 doubao-1.5-pro。"}}},"errors":null}</script>
</body></html>
```

- [ ] **Step 2: 写失败测试**

`backend/tests/test_adapter_volcengine.py`：

```python
from datetime import datetime
from pathlib import Path

import pytest

from app.adapters import AdapterError
from app.adapters.volcengine import _new_doc_items, parse_doc_page

HTML = (Path(__file__).parent / "fixtures" / "volcengine.html").read_text(encoding="utf-8")


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
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_adapter_volcengine.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 4: 实现**

`backend/app/adapters/volcengine.py`：

```python
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
```

（`_parse_time` 必须转 **UTC** 再去时区——fixture 中 `2026-07-08T03:46:49Z` → naive `2026-07-08 03:46:49`，与测试断言一致；绝不能 `astimezone(None)` 转本地时区。）

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_adapter_volcengine.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 6: 全量回归**

Run: `cd backend && python -m pytest tests -v`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/adapters/volcengine.py backend/tests/
git commit -m "feat: 火山引擎适配器——_ROUTER_DATA 更新检测 + 产品公告子树新文档检测"
```

---

### Task 6: 邮件模块（mailer）

**Files:**
- Create: `backend/app/mailer.py`
- Test: `backend/tests/test_mailer.py`

**Interfaces:**
- Produces: `send_email(recipients: list[str], subject: str, html: str) -> None`（smtplib SSL 发送，SMTP 未配置抛 `RuntimeError`）；`build_notices_email(notices) -> tuple[str, str]`（入参为 Notice ORM 对象列表，需可访问 `n.source.name`）；`send_login_code(email: str, code: str) -> None`
- Consumes: Task 1 的 `settings`、`Notice`/`Source` 模型
- **约定：其他模块调用邮件必须写成 `from . import mailer` + `mailer.send_email(...)`，保证测试 monkeypatch `app.mailer.send_email` 生效。`send_login_code` 内部调用本模块全局 `send_email`（同样会被 patch 截获）。**

- [ ] **Step 1: 写失败测试**

`backend/tests/test_mailer.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_mailer.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

`backend/app/mailer.py`：

```python
import json
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from .config import settings


def send_email(recipients: list[str], subject: str, html: str) -> None:
    if not settings.smtp_user or not settings.smtp_auth_code:
        raise RuntimeError("SMTP 未配置：请设置 SMTP_USER 和 SMTP_AUTH_CODE 环境变量")
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("模型公告提醒", settings.smtp_user))
    msg["To"] = ", ".join(recipients)
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_auth_code)
        smtp.sendmail(settings.smtp_user, recipients, msg.as_string())


def build_notices_email(notices) -> tuple[str, str]:
    first = notices[0]
    if len(notices) == 1:
        subject = f"【模型公告提醒】{first.source.name}: {first.title}"
    else:
        subject = f"【模型公告提醒】{first.source.name}等 {len(notices)} 条新公告"
    blocks = []
    for n in notices:
        published = n.published_at.strftime("%Y-%m-%d %H:%M") if n.published_at else "未知"
        keywords = "、".join(json.loads(n.matched_keywords or "[]"))
        excerpt = (n.content or "")[:300]
        blocks.append(
            f'<div style="border:1px solid #ddd;border-radius:8px;padding:16px;margin-bottom:16px;">'
            f'<div style="color:#888;font-size:12px;">{n.source.name} · {published}'
            f'{" · 命中：" + keywords if keywords else ""}</div>'
            f'<h3 style="margin:8px 0;"><a href="{n.url}">{n.title}</a></h3>'
            f'<p style="color:#444;margin:0;">{excerpt}</p></div>'
        )
    html = (
        "<div style='font-family:sans-serif;max-width:680px;'>"
        + "".join(blocks)
        + "<p style='color:#aaa;font-size:12px;'>模型公告聚合平台自动发送</p></div>"
    )
    return subject, html


def send_login_code(email: str, code: str) -> None:
    send_email(
        [email],
        "【模型公告平台】登录验证码",
        f"<p>你的登录验证码是：<b style='font-size:20px'>{code}</b>，10 分钟内有效。</p>",
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_mailer.py -v`
Expected: PASS（3 个测试）

- [ ] **Step 5: Commit**

```bash
git add backend/app/mailer.py backend/tests/test_mailer.py
git commit -m "feat: 邮件模块——QQ SMTP 发送与通知/验证码邮件构建"
```

---

### Task 7: 抓取通知流水线（pipeline）

**Files:**
- Create: `backend/app/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Produces: `fetch_source(db, source) -> int`（新条目数；内部处理去重/基线/匹配/源状态）；`send_pending(db) -> int`（合并发送待发条目，成功写 notified_at）；`run_round(db) -> dict`（`{"sources": int, "new_items": int, "notified": int}`）
- Consumes: `fetch_items`/`AdapterError`（Task 3）、`find_matches`（Task 2）、`mailer`（Task 6）、模型与 `get_session`（Task 1）
- **待发送条件（全库范围，天然含重试）：`matched=True 且 notified_at 为空 且 is_baseline=False`**

- [ ] **Step 1: 写失败测试**

`backend/tests/test_pipeline.py`：

```python
import json
from datetime import datetime

import pytest
from sqlalchemy import select

from app import pipeline
from app.adapters import AdapterError, FetchedItem
from app.models import Keyword, Notice, Source, User


@pytest.fixture()
def source(db):
    s = Source(name="测试源", type="rss", url="http://feed")
    db.add(s)
    db.add_all([Keyword(word="模型", enabled=True), Keyword(word="下线", enabled=True),
                Keyword(word="停用词", enabled=False)])
    db.commit()
    return s


def _stub_items(monkeypatch, items):
    monkeypatch.setattr(pipeline, "fetch_items", lambda t, u: items)


def test_first_fetch_marks_baseline_and_no_notify(db, source, monkeypatch, sent_emails):
    db.add(User(email="a@qq.com", notify_enabled=True))
    db.commit()
    _stub_items(monkeypatch, [FetchedItem(title="老模型下线公告", url="http://n/1")])
    assert pipeline.fetch_source(db, source) == 1
    assert pipeline.send_pending(db) == 0  # 基线不发
    n = db.scalars(select(Notice)).one()
    assert n.is_baseline and n.matched
    assert json.loads(n.matched_keywords) == ["模型", "下线"]
    assert sent_emails == []
    assert source.last_fetch_status == "ok"


def test_second_fetch_dedupes_and_notifies_matched_only(db, source, monkeypatch, sent_emails):
    db.add_all([User(email="a@qq.com", notify_enabled=True),
                User(email="b@qq.com", notify_enabled=False)])
    db.commit()
    _stub_items(monkeypatch, [FetchedItem(title="旧条目", url="http://n/1")])
    pipeline.fetch_source(db, source)  # 基线
    _stub_items(monkeypatch, [
        FetchedItem(title="旧条目", url="http://n/1"),          # 重复，跳过
        FetchedItem(title="新模型下线通知", url="http://n/2"),   # 命中
        FetchedItem(title="无关价格调整", url="http://n/3"),     # 不命中
    ])
    assert pipeline.fetch_source(db, source) == 2
    assert pipeline.send_pending(db) == 1
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == ["a@qq.com"]  # notify_enabled=False 的不收
    assert "新模型下线通知" in sent_emails[0]["html"]


def test_multiple_pending_merged_into_one_email(db, source, monkeypatch, sent_emails):
    db.add(User(email="a@qq.com", notify_enabled=True))
    db.commit()
    _stub_items(monkeypatch, [FetchedItem(title="基线", url="http://n/0")])
    pipeline.fetch_source(db, source)
    _stub_items(monkeypatch, [FetchedItem(title="模型公告一", url="http://n/1"),
                              FetchedItem(title="模型公告二", url="http://n/2")])
    pipeline.fetch_source(db, source)
    assert pipeline.send_pending(db) == 2
    assert len(sent_emails) == 1  # 合并一封


def test_send_failure_keeps_pending_for_retry(db, source, monkeypatch):
    db.add(User(email="a@qq.com", notify_enabled=True))
    db.commit()
    _stub_items(monkeypatch, [FetchedItem(title="基线", url="http://n/0")])
    pipeline.fetch_source(db, source)
    _stub_items(monkeypatch, [FetchedItem(title="模型下线", url="http://n/1")])
    pipeline.fetch_source(db, source)

    def boom(recipients, subject, html):
        raise RuntimeError("SMTP down")

    monkeypatch.setattr("app.mailer.send_email", boom)
    assert pipeline.send_pending(db) == 0  # 失败，不标记
    n = db.scalars(select(Notice).where(Notice.url == "http://n/1")).one()
    assert n.notified_at is None  # 下一轮重试


def test_adapter_error_records_source_status(db, source, monkeypatch):
    def raise_err(t, u):
        raise AdapterError("网络超时")

    monkeypatch.setattr(pipeline, "fetch_items", raise_err)
    assert pipeline.fetch_source(db, source) == 0
    assert source.last_fetch_status == "error"
    assert "网络超时" in source.last_error


def test_run_round_covers_enabled_sources_only(db, monkeypatch, sent_emails):
    s1 = Source(name="启用源", type="rss", url="http://a", enabled=True)
    s2 = Source(name="停用源", type="rss", url="http://b", enabled=False)
    db.add_all([s1, s2, Keyword(word="模型", enabled=True)])
    db.commit()
    called = []
    monkeypatch.setattr(pipeline, "fetch_items", lambda t, u: called.append(u) or [])
    result = pipeline.run_round(db)
    assert called == ["http://a"]
    assert result == {"sources": 1, "new_items": 0, "notified": 0}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_pipeline.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

`backend/app/pipeline.py`：

```python
import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import mailer
from .adapters import AdapterError, fetch_items
from .matching import find_matches
from .models import Keyword, Notice, Source, User

logger = logging.getLogger(__name__)


def fetch_source(db: Session, source: Source) -> int:
    """抓取单个源：去重入库、首次抓取标基线、关键词匹配、更新源状态。返回新条目数。"""
    try:
        items = fetch_items(source.type, source.url)
    except AdapterError as e:
        source.last_fetch_at = datetime.utcnow()
        source.last_fetch_status = "error"
        source.last_error = str(e)[:1000]
        db.commit()
        logger.warning("源「%s」抓取失败: %s", source.name, e)
        return 0
    is_first_fetch = (
        db.scalars(select(Notice.id).where(Notice.source_id == source.id).limit(1)).first()
        is None
    )
    words = list(db.scalars(select(Keyword.word).where(Keyword.enabled == True)))  # noqa: E712
    existing = set(db.scalars(select(Notice.url).where(Notice.source_id == source.id)))
    new_count = 0
    for item in items:
        if item.url in existing:
            continue
        existing.add(item.url)
        matches = find_matches(item.title, item.content, words)
        db.add(Notice(
            source_id=source.id,
            title=item.title[:500],
            url=item.url[:1000],
            content=item.content[:5000],
            published_at=item.published_at or datetime.utcnow(),
            matched=bool(matches),
            matched_keywords=json.dumps(matches, ensure_ascii=False),
            is_baseline=is_first_fetch,
        ))
        new_count += 1
    source.last_fetch_at = datetime.utcnow()
    source.last_fetch_status = "ok"
    source.last_error = None
    db.commit()
    return new_count


def send_pending(db: Session) -> int:
    """把待发送的命中条目合并为一封邮件群发；失败不标记（下一轮自动重试）。"""
    pending = list(db.scalars(
        select(Notice)
        .where(Notice.matched == True, Notice.notified_at == None,  # noqa: E711,E712
               Notice.is_baseline == False)  # noqa: E712
        .order_by(Notice.published_at.desc())
    ))
    if not pending:
        return 0
    recipients = list(db.scalars(select(User.email).where(User.notify_enabled == True)))  # noqa: E712
    if not recipients:
        return 0
    subject, html = mailer.build_notices_email(pending)
    try:
        mailer.send_email(recipients, subject, html)
    except Exception as e:
        logger.error("通知邮件发送失败，下一轮重试: %s", e)
        return 0
    now = datetime.utcnow()
    for n in pending:
        n.notified_at = now
    db.commit()
    return len(pending)


def run_round(db: Session) -> dict:
    """一轮完整流水线：抓取所有启用源 + 发送待发通知。"""
    sources = list(db.scalars(select(Source).where(Source.enabled == True)))  # noqa: E712
    total_new = sum(fetch_source(db, s) for s in sources)
    notified = send_pending(db)
    logger.info("本轮完成：%d 个源，新条目 %d，通知 %d 条", len(sources), total_new, notified)
    return {"sources": len(sources), "new_items": total_new, "notified": notified}
```

注意 `test_send_failure_keeps_pending_for_retry` 中 monkeypatch 的是 `app.mailer.send_email`，而 `send_pending` 调用 `mailer.send_email(...)`（模块属性访问），运行时取到的是被 patch 后的函数——这正是接口约定要求 `from . import mailer` 的原因。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_pipeline.py -v`
Expected: PASS（6 个测试）

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline.py backend/tests/test_pipeline.py
git commit -m "feat: 抓取-去重-筛选-合并通知流水线（基线导入与失败重试幂等）"
```

---

### Task 8: 认证模块与认证路由

**Files:**
- Create: `backend/app/auth.py`、`backend/app/routers/__init__.py`、`backend/app/routers/auth_users.py`
- Test: `backend/tests/test_auth.py`（依赖 Task 9 的 `app.main`，因此本任务同时创建**最小** `backend/app/main.py`，Task 9 再扩充）

**Interfaces:**
- Produces: `app.auth` 的 `COOKIE_NAME="session"`、`SESSION_MAX_AGE`、`EMAIL_RE`、`sign_session(email) -> str`、`read_session(token) -> str | None`、`create_login_code(db, email) -> str`（60 秒限流抛 HTTPException 429）、`verify_login_code(db, email, code) -> bool`、`get_current_user`（FastAPI 依赖）；路由 `POST /api/auth/request-code`、`POST /api/auth/verify`、`POST /api/auth/logout`、`GET /api/me`、`PATCH /api/me`、`GET /api/users`；最小 `app.main.app`
- Consumes: Task 1 的 `settings`/模型/`get_session`、Task 6 的 `mailer.send_login_code`

- [ ] **Step 1: 在 conftest 增加 client fixture**

在 `backend/tests/conftest.py` 末尾追加：

```python
@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import app

    def override():
        yield db

    app.dependency_overrides[get_session] = override
    # 不用 with（避免触发 lifespan 里的 init_db/scheduler），直接请求即可
    yield TestClient(app)
    app.dependency_overrides.clear()
```

- [ ] **Step 2: 写失败测试**

`backend/tests/test_auth.py`：

```python
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import LoginCode, User


def _request_code(client, email="user@qq.com"):
    return client.post("/api/auth/request-code", json={"email": email})


def _login(client, db, email="user@qq.com"):
    _request_code(client, email)
    code = db.scalars(select(LoginCode).where(LoginCode.email == email)).first().code
    return client.post("/api/auth/verify", json={"email": email, "code": code})


def test_request_code_sends_email(client, db, sent_emails):
    resp = _request_code(client)
    assert resp.status_code == 200
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == ["user@qq.com"]
    code = db.scalars(select(LoginCode)).one()
    assert len(code.code) == 6 and code.code in sent_emails[0]["html"]


def test_request_code_invalid_email(client, sent_emails):
    assert _request_code(client, "not-an-email").status_code == 422
    assert sent_emails == []


def test_request_code_rate_limited_60s(client, db, sent_emails):
    assert _request_code(client).status_code == 200
    assert _request_code(client).status_code == 429
    assert len(sent_emails) == 1


def test_verify_creates_user_and_sets_cookie(client, db, sent_emails):
    resp = _login(client, db)
    assert resp.status_code == 200
    assert "session" in resp.cookies
    user = db.scalars(select(User)).one()
    assert user.email == "user@qq.com" and user.notify_enabled


def test_verify_wrong_code(client, db, sent_emails):
    _request_code(client)
    resp = client.post("/api/auth/verify", json={"email": "user@qq.com", "code": "000000"})
    assert resp.status_code == 400


def test_code_single_use(client, db, sent_emails):
    _request_code(client)
    code = db.scalars(select(LoginCode)).one().code
    assert client.post("/api/auth/verify", json={"email": "user@qq.com", "code": code}).status_code == 200
    assert client.post("/api/auth/verify", json={"email": "user@qq.com", "code": code}).status_code == 400


def test_expired_code_rejected(client, db, sent_emails):
    _request_code(client)
    record = db.scalars(select(LoginCode)).one()
    record.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    resp = client.post("/api/auth/verify", json={"email": "user@qq.com", "code": record.code})
    assert resp.status_code == 400


def test_me_requires_login(client):
    assert client.get("/api/me").status_code == 401


def test_me_and_notify_toggle(client, db, sent_emails):
    _login(client, db)
    assert client.get("/api/me").json() == {"email": "user@qq.com", "notify_enabled": True}
    resp = client.patch("/api/me", json={"notify_enabled": False})
    assert resp.json()["notify_enabled"] is False


def test_users_list_requires_login_and_lists_members(client, db, sent_emails):
    assert client.get("/api/users").status_code == 401
    _login(client, db)
    users = client.get("/api/users").json()
    assert [u["email"] for u in users] == ["user@qq.com"]


def test_logout_clears_cookie(client, db, sent_emails):
    _login(client, db)
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL（`ModuleNotFoundError: app.main`）

- [ ] **Step 4: 实现 auth.py、认证路由与最小 main.py**

`backend/app/auth.py`：

```python
import random
import re
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_session
from .models import LoginCode, User

COOKIE_NAME = "session"
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 天
CODE_TTL_MINUTES = 10
RESEND_INTERVAL_SECONDS = 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="session")


def sign_session(email: str) -> str:
    return _serializer().dumps(email)


def read_session(token: str) -> str | None:
    try:
        return _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def create_login_code(db: Session, email: str) -> str:
    latest = db.scalars(
        select(LoginCode).where(LoginCode.email == email)
        .order_by(LoginCode.created_at.desc()).limit(1)
    ).first()
    if latest and (datetime.utcnow() - latest.created_at).total_seconds() < RESEND_INTERVAL_SECONDS:
        raise HTTPException(status_code=429, detail="请求过于频繁，请 60 秒后再试")
    code = f"{random.randint(0, 999999):06d}"
    db.add(LoginCode(
        email=email, code=code,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
    ))
    db.commit()
    return code


def verify_login_code(db: Session, email: str, code: str) -> bool:
    record = db.scalars(
        select(LoginCode).where(
            LoginCode.email == email, LoginCode.code == code,
            LoginCode.used == False,  # noqa: E712
            LoginCode.expires_at > datetime.utcnow(),
        ).order_by(LoginCode.created_at.desc()).limit(1)
    ).first()
    if not record:
        return False
    record.used = True
    db.commit()
    return True


def get_current_user(request: Request, db: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    email = read_session(token) if token else None
    if not email:
        raise HTTPException(status_code=401, detail="未登录")
    user = db.scalars(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
```

`backend/app/routers/__init__.py`：空文件。

`backend/app/routers/auth_users.py`：

```python
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, mailer
from ..db import get_session
from ..models import User

router = APIRouter(prefix="/api")


class RequestCodeBody(BaseModel):
    email: str


class VerifyBody(BaseModel):
    email: str
    code: str


class MePatch(BaseModel):
    notify_enabled: bool


@router.post("/auth/request-code")
def request_code(body: RequestCodeBody, db: Session = Depends(get_session)):
    email = body.email.strip().lower()
    if not auth.EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="邮箱格式不正确")
    code = auth.create_login_code(db, email)
    try:
        mailer.send_login_code(email, code)
    except Exception:
        raise HTTPException(status_code=502, detail="验证码邮件发送失败，请检查 SMTP 配置")
    return {"message": "验证码已发送"}


@router.post("/auth/verify")
def verify(body: VerifyBody, response: Response, db: Session = Depends(get_session)):
    email = body.email.strip().lower()
    if not auth.verify_login_code(db, email, body.code.strip()):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    user = db.scalars(select(User).where(User.email == email)).first()
    if not user:
        user = User(email=email)
        db.add(user)
    user.last_login_at = datetime.utcnow()
    db.commit()
    response.set_cookie(
        auth.COOKIE_NAME, auth.sign_session(email),
        max_age=auth.SESSION_MAX_AGE, httponly=True, samesite="lax",
    )
    return {"email": email}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME)
    return {"message": "已退出"}


@router.get("/me")
def me(user: User = Depends(auth.get_current_user)):
    return {"email": user.email, "notify_enabled": user.notify_enabled}


@router.patch("/me")
def update_me(
    body: MePatch,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_session),
):
    user.notify_enabled = body.notify_enabled
    db.commit()
    return {"email": user.email, "notify_enabled": user.notify_enabled}


@router.get("/users")
def list_users(
    user: User = Depends(auth.get_current_user), db: Session = Depends(get_session)
):
    users = db.scalars(select(User).order_by(User.created_at)).all()
    return [
        {"email": u.email, "notify_enabled": u.notify_enabled, "last_login_at": u.last_login_at}
        for u in users
    ]
```

`backend/app/main.py`（最小版，Task 10 扩充 lifespan/scheduler）：

```python
from fastapi import FastAPI

from .routers import auth_users

app = FastAPI(title="模型公告聚合平台")
app.include_router(auth_users.router)
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: PASS（11 个测试）

- [ ] **Step 6: Commit**

```bash
git add backend/app/ backend/tests/
git commit -m "feat: 邮箱验证码登录——限流、一次性验证码、Cookie 会话与成员接口"
```

---

### Task 9: 业务 API（公告 / 源 / 关键词 / 手动抓取）

**Files:**
- Create: `backend/app/routers/notices.py`、`backend/app/routers/sources.py`、`backend/app/routers/keywords.py`
- Modify: `backend/app/main.py`（挂载三个新路由）
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces:
  - `GET /api/notices?source_id=&matched_only=true&q=&page=1&page_size=20` → `{total, page, page_size, items: [{id, source_id, source_name, title, url, excerpt, published_at, matched, matched_keywords}]}`
  - `GET /api/sources` → `[{id, name, type, url, enabled, is_builtin, last_fetch_at, last_fetch_status, last_error}]`（免登录）
  - `POST /api/sources`（登录，201，type 限 rss/webpage）、`PATCH /api/sources/{id}`、`DELETE /api/sources/{id}`（内置源 400；204）、`POST /api/sources/{id}/fetch` → `{new_items, notified}`
  - `GET /api/keywords` → `[{id, word, enabled}]`（免登录）；`POST /api/keywords`（201，重复词 409）、`PATCH /api/keywords/{id}`、`DELETE /api/keywords/{id}`（204）（均需登录）
- Consumes: Task 7 的 `pipeline.fetch_source/send_pending`、Task 8 的 `get_current_user`、Task 1 的模型

- [ ] **Step 1: 写失败测试**

`backend/tests/test_api.py`：

```python
import json

from sqlalchemy import select

from app.models import Keyword, LoginCode, Notice, Source


def _login(client, db, email="admin@qq.com"):
    client.post("/api/auth/request-code", json={"email": email})
    code = db.scalars(select(LoginCode).where(LoginCode.email == email)).first().code
    client.post("/api/auth/verify", json={"email": email, "code": code})


def _seed(db):
    src = Source(name="阿里云公告", type="aliyun_rss", url="http://a", is_builtin=True)
    db.add(src)
    db.commit()
    db.add_all([
        Notice(source_id=src.id, title="模型下线通知", url="http://n/1", content="正文A",
               matched=True, matched_keywords=json.dumps(["模型", "下线"], ensure_ascii=False)),
        Notice(source_id=src.id, title="价格调整公告", url="http://n/2", content="正文B",
               matched=False, matched_keywords="[]"),
    ])
    db.commit()
    return src


def test_notices_default_matched_only(client, db):
    _seed(db)
    data = client.get("/api/notices").json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["title"] == "模型下线通知"
    assert item["source_name"] == "阿里云公告"
    assert item["matched_keywords"] == ["模型", "下线"]


def test_notices_all_and_search(client, db):
    _seed(db)
    assert client.get("/api/notices?matched_only=false").json()["total"] == 2
    assert client.get("/api/notices?matched_only=false&q=价格").json()["total"] == 1


def test_sources_list_public(client, db):
    _seed(db)
    data = client.get("/api/sources").json()
    assert data[0]["name"] == "阿里云公告" and data[0]["is_builtin"] is True


def test_create_source_requires_login(client, db):
    body = {"name": "自定义", "type": "rss", "url": "https://x.com/feed.xml"}
    assert client.post("/api/sources", json=body).status_code == 401
    _login(client, db)
    resp = client.post("/api/sources", json=body)
    assert resp.status_code == 201
    assert resp.json()["is_builtin"] is False


def test_create_source_validates_type_and_url(client, db):
    _login(client, db)
    assert client.post("/api/sources", json={"name": "x", "type": "volcengine", "url": "https://x.com"}).status_code == 422
    assert client.post("/api/sources", json={"name": "x", "type": "rss", "url": "ftp://x.com"}).status_code == 422


def test_patch_and_delete_source(client, db):
    src = _seed(db)
    _login(client, db)
    assert client.patch(f"/api/sources/{src.id}", json={"enabled": False}).json()["enabled"] is False
    # 内置源不可删除
    assert client.delete(f"/api/sources/{src.id}").status_code == 400
    custom = client.post("/api/sources", json={"name": "c", "type": "rss", "url": "https://c.com/f"}).json()
    assert client.delete(f"/api/sources/{custom['id']}").status_code == 204


def test_manual_fetch(client, db, monkeypatch, sent_emails):
    src = _seed(db)
    _login(client, db)
    from app.adapters import FetchedItem
    from app import pipeline

    monkeypatch.setattr(pipeline, "fetch_items",
                        lambda t, u: [FetchedItem(title="新模型下线", url="http://n/9")])
    db.add(Keyword(word="下线", enabled=True))
    db.commit()
    resp = client.post(f"/api/sources/{src.id}/fetch")
    assert resp.status_code == 200
    assert resp.json()["new_items"] == 1


def test_keywords_crud(client, db):
    assert client.get("/api/keywords").json() == []
    assert client.post("/api/keywords", json={"word": "下线"}).status_code == 401
    _login(client, db)
    created = client.post("/api/keywords", json={"word": "下线"})
    assert created.status_code == 201
    assert client.post("/api/keywords", json={"word": "下线"}).status_code == 409
    kid = created.json()["id"]
    assert client.patch(f"/api/keywords/{kid}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"/api/keywords/{kid}").status_code == 204
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_api.py -v`
Expected: FAIL（404，路由不存在）

- [ ] **Step 3: 实现三个路由**

`backend/app/routers/notices.py`：

```python
import json

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Notice

router = APIRouter(prefix="/api")


@router.get("/notices")
def list_notices(
    source_id: int | None = None,
    matched_only: bool = True,
    q: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_session),
):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    stmt = select(Notice)
    if source_id:
        stmt = stmt.where(Notice.source_id == source_id)
    if matched_only:
        stmt = stmt.where(Notice.matched == True)  # noqa: E712
    if q:
        stmt = stmt.where(Notice.title.contains(q))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(Notice.published_at.desc(), Notice.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": n.id,
                "source_id": n.source_id,
                "source_name": n.source.name,
                "title": n.title,
                "url": n.url,
                "excerpt": (n.content or "")[:300],
                "published_at": n.published_at,
                "matched": n.matched,
                "matched_keywords": json.loads(n.matched_keywords or "[]"),
            }
            for n in rows
        ],
    }
```

`backend/app/routers/sources.py`：

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pipeline
from ..auth import get_current_user
from ..db import get_session
from ..models import Source

router = APIRouter(prefix="/api")


class SourceCreate(BaseModel):
    name: str
    type: str
    url: str


class SourcePatch(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None


def _to_dict(s: Source) -> dict:
    return {
        "id": s.id, "name": s.name, "type": s.type, "url": s.url,
        "enabled": s.enabled, "is_builtin": s.is_builtin,
        "last_fetch_at": s.last_fetch_at, "last_fetch_status": s.last_fetch_status,
        "last_error": s.last_error,
    }


def _get_or_404(db: Session, source_id: int) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="源不存在")
    return source


@router.get("/sources")
def list_sources(db: Session = Depends(get_session)):
    return [_to_dict(s) for s in db.scalars(select(Source).order_by(Source.id)).all()]


@router.post("/sources", status_code=201)
def create_source(
    body: SourceCreate, db: Session = Depends(get_session), _=Depends(get_current_user)
):
    if body.type not in ("rss", "webpage"):
        raise HTTPException(status_code=422, detail="自定义源类型仅支持 rss 或 webpage")
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="URL 必须以 http(s):// 开头")
    source = Source(name=body.name.strip(), type=body.type, url=body.url.strip())
    db.add(source)
    db.commit()
    return _to_dict(source)


@router.patch("/sources/{source_id}")
def update_source(
    source_id: int, body: SourcePatch,
    db: Session = Depends(get_session), _=Depends(get_current_user),
):
    source = _get_or_404(db, source_id)
    if body.name is not None:
        source.name = body.name.strip()
    if body.url is not None:
        if not body.url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="URL 必须以 http(s):// 开头")
        source.url = body.url.strip()
    if body.enabled is not None:
        source.enabled = body.enabled
    db.commit()
    return _to_dict(source)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(
    source_id: int, db: Session = Depends(get_session), _=Depends(get_current_user)
):
    source = _get_or_404(db, source_id)
    if source.is_builtin:
        raise HTTPException(status_code=400, detail="内置源不可删除，只能停用")
    db.delete(source)  # cascade 删除其 notices
    db.commit()


@router.post("/sources/{source_id}/fetch")
def fetch_now(
    source_id: int, db: Session = Depends(get_session), _=Depends(get_current_user)
):
    source = _get_or_404(db, source_id)
    new_items = pipeline.fetch_source(db, source)
    notified = pipeline.send_pending(db)
    return {"new_items": new_items, "notified": notified,
            "last_fetch_status": source.last_fetch_status, "last_error": source.last_error}
```

`backend/app/routers/keywords.py`：

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_session
from ..models import Keyword

router = APIRouter(prefix="/api")


class KeywordCreate(BaseModel):
    word: str


class KeywordPatch(BaseModel):
    enabled: bool


@router.get("/keywords")
def list_keywords(db: Session = Depends(get_session)):
    return [
        {"id": k.id, "word": k.word, "enabled": k.enabled}
        for k in db.scalars(select(Keyword).order_by(Keyword.id)).all()
    ]


@router.post("/keywords", status_code=201)
def create_keyword(
    body: KeywordCreate, db: Session = Depends(get_session), _=Depends(get_current_user)
):
    word = body.word.strip()
    if not word:
        raise HTTPException(status_code=422, detail="关键词不能为空")
    if db.scalars(select(Keyword).where(Keyword.word == word)).first():
        raise HTTPException(status_code=409, detail="关键词已存在")
    keyword = Keyword(word=word, enabled=True)
    db.add(keyword)
    db.commit()
    return {"id": keyword.id, "word": keyword.word, "enabled": keyword.enabled}


@router.patch("/keywords/{keyword_id}")
def update_keyword(
    keyword_id: int, body: KeywordPatch,
    db: Session = Depends(get_session), _=Depends(get_current_user),
):
    keyword = db.get(Keyword, keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="关键词不存在")
    keyword.enabled = body.enabled
    db.commit()
    return {"id": keyword.id, "word": keyword.word, "enabled": keyword.enabled}


@router.delete("/keywords/{keyword_id}", status_code=204)
def delete_keyword(
    keyword_id: int, db: Session = Depends(get_session), _=Depends(get_current_user)
):
    keyword = db.get(Keyword, keyword_id)
    if not keyword:
        raise HTTPException(status_code=404, detail="关键词不存在")
    db.delete(keyword)
    db.commit()
```

修改 `backend/app/main.py` 为：

```python
from fastapi import FastAPI

from .routers import auth_users, keywords, notices, sources

app = FastAPI(title="模型公告聚合平台")
for r in (notices.router, sources.router, keywords.router, auth_users.router):
    app.include_router(r)
```

- [ ] **Step 4: 运行确认通过（全量）**

Run: `cd backend && python -m pytest tests -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/ backend/tests/test_api.py
git commit -m "feat: 公告/源/关键词 REST API 与手动抓取接口"
```

---

### Task 10: 后端组装——lifespan、调度器与健康检查

**Files:**
- Create: `backend/app/scheduler.py`
- Modify: `backend/app/main.py`（加 lifespan：init_db + 条件启动调度器；加 `GET /api/health`）
- Test: `backend/tests/test_main.py`

**Interfaces:**
- Produces: `app.scheduler.start_scheduler() -> BackgroundScheduler`（interval 触发，首跑延迟 15 秒）；`GET /api/health` → `{"status": "ok"}`；完整可运行的 `uvicorn app.main:app`
- Consumes: Task 7 的 `run_round`、Task 1 的 `SessionLocal/init_db/settings`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_main.py`：

```python
def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_main.py -v`
Expected: FAIL（404）

- [ ] **Step 3: 实现 scheduler 与最终 main.py**

`backend/app/scheduler.py`：

```python
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .db import SessionLocal
from .pipeline import run_round

logger = logging.getLogger(__name__)


def _job() -> None:
    with SessionLocal() as db:
        try:
            run_round(db)
        except Exception:
            logger.exception("定时抓取任务执行异常")


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _job, "interval",
        minutes=settings.fetch_interval_minutes,
        next_run_time=datetime.now() + timedelta(seconds=15),  # 启动后 15 秒先跑一轮
    )
    scheduler.start()
    logger.info("调度器已启动，每 %d 分钟抓取一轮", settings.fetch_interval_minutes)
    return scheduler
```

`backend/app/main.py` 最终版：

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import init_db
from .routers import auth_users, keywords, notices, sources
from .scheduler import start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = start_scheduler() if settings.enable_scheduler else None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="模型公告聚合平台", lifespan=lifespan)
for r in (notices.router, sources.router, keywords.router, auth_users.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: 运行全量测试确认通过**

Run: `cd backend && python -m pytest tests -v`
Expected: 全部 PASS（conftest 已设 `ENABLE_SCHEDULER=0`，且 client fixture 不触发 lifespan）

- [ ] **Step 5: 真实冒烟——起服务打真实源**

```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

另开终端验证（PowerShell 用 `curl.exe`）：

```bash
curl http://localhost:8000/api/health          # {"status":"ok"}
curl http://localhost:8000/api/sources         # 两个内置源
# 等待约 20 秒（调度器首跑）后：
curl "http://localhost:8000/api/notices?page_size=5"
```

Expected: notices 返回真实抓到的条目（阿里云 RSS + 火山公告，全部 `is_baseline` 基线导入，无邮件外发——未配置 SMTP 时 send_pending 无待发条目，因为基线不发）。若源站临时不可达，`/api/sources` 的 `last_error` 会显示原因，属预期行为。验证完 Ctrl+C 停服。

- [ ] **Step 6: Commit**

```bash
git add backend/app/
git commit -m "feat: 后端组装——lifespan 初始化、APScheduler 定时抓取与健康检查"
```

---

### Task 11: 前端脚手架（Next.js + rewrites 代理 + API 封装 + 导航）

**Files:**
- Create: `frontend/package.json`、`frontend/tsconfig.json`、`frontend/next.config.js`、`frontend/next-env.d.ts`、`frontend/lib/api.ts`、`frontend/app/layout.tsx`、`frontend/app/globals.css`、`frontend/app/components/NavBar.tsx`、`frontend/app/page.tsx`（临时占位，Task 12 替换）

**Interfaces:**
- Produces: `lib/api.ts` 的 `api<T>(path, options?) -> Promise<T>` 与类型 `NoticeItem/NoticeList/SourceItem/KeywordItem/Me`；全局布局与导航；`/api/*` 相对路径经 rewrites 代理到后端
- Consumes: Task 9/10 的后端 API

- [ ] **Step 1: 创建配置文件**

`frontend/package.json`：

```json
{
  "name": "notice-frontend",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "^14.2.5",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "typescript": "^5"
  }
}
```

`frontend/next.config.js`：

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // 前端与后端同源化：浏览器只请求相对路径 /api/*，由 Next 服务端代理
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

module.exports = nextConfig;
```

`frontend/tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`frontend/next-env.d.ts`：

```ts
/// <reference types="next" />
/// <reference types="next/image-types/global" />
```

安装依赖：

```bash
cd frontend
npm install
```

- [ ] **Step 2: 写 API 封装**

`frontend/lib/api.ts`：

```ts
export interface NoticeItem {
  id: number;
  source_id: number;
  source_name: string;
  title: string;
  url: string;
  excerpt: string;
  published_at: string;
  matched: boolean;
  matched_keywords: string[];
}

export interface NoticeList {
  total: number;
  page: number;
  page_size: number;
  items: NoticeItem[];
}

export interface SourceItem {
  id: number;
  name: string;
  type: string;
  url: string;
  enabled: boolean;
  is_builtin: boolean;
  last_fetch_at: string | null;
  last_fetch_status: string | null;
  last_error: string | null;
}

export interface KeywordItem {
  id: number;
  word: string;
  enabled: boolean;
}

export interface Me {
  email: string;
  notify_enabled: boolean;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as { detail?: string }).detail || `请求失败 (${res.status})`);
  }
  return data as T;
}

export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleString("zh-CN", {
    hour12: false,
  });
}
```

（后端存 naive UTC、FastAPI 序列化不带时区后缀，所以 `formatTime` 补 `Z` 后按本地时区展示。）

- [ ] **Step 3: 写布局、样式与导航**

`frontend/app/globals.css`：

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; color: #1a1a1a; background: #f6f7f9; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }

.nav { background: #fff; border-bottom: 1px solid #e5e7eb; padding: 0 24px; display: flex; align-items: center; height: 56px; gap: 24px; }
.nav .brand { font-weight: 700; font-size: 16px; color: #111; }
.nav a.link { color: #4b5563; font-size: 14px; }
.nav a.link:hover { color: #111; text-decoration: none; }
.nav .spacer { flex: 1; }
.nav .user { font-size: 13px; color: #6b7280; }

.container { max-width: 960px; margin: 24px auto; padding: 0 16px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px 20px; margin-bottom: 12px; }
.card h3 { font-size: 15px; margin: 6px 0; }
.meta { font-size: 12px; color: #6b7280; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.tag { background: #eef2ff; color: #4338ca; border-radius: 4px; padding: 1px 8px; font-size: 12px; }
.kw { background: #fef3c7; color: #92400e; border-radius: 4px; padding: 1px 6px; font-size: 12px; }
.excerpt { font-size: 13px; color: #4b5563; margin-top: 6px; line-height: 1.6; }

.toolbar { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
select, input[type="text"], input[type="email"] { border: 1px solid #d1d5db; border-radius: 6px; padding: 6px 10px; font-size: 14px; background: #fff; }
button { border: 1px solid #d1d5db; border-radius: 6px; padding: 6px 14px; font-size: 14px; background: #fff; cursor: pointer; }
button:hover { background: #f3f4f6; }
button.primary { background: #2563eb; border-color: #2563eb; color: #fff; }
button.primary:hover { background: #1d4ed8; }
button.danger { color: #dc2626; }
button:disabled { opacity: 0.5; cursor: not-allowed; }

table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 10px 12px; font-size: 13px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }
th { background: #f9fafb; color: #6b7280; font-weight: 500; }
.status-ok { color: #16a34a; }
.status-error { color: #dc2626; }
.error-box { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 8px; padding: 10px 14px; font-size: 13px; margin-bottom: 12px; }
.form-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.pager { display: flex; gap: 8px; align-items: center; margin-top: 16px; font-size: 13px; color: #6b7280; }
```

`frontend/app/layout.tsx`：

```tsx
import "./globals.css";
import NavBar from "./components/NavBar";

export const metadata = { title: "模型公告聚合平台" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <NavBar />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
```

`frontend/app/components/NavBar.tsx`：

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Me } from "@/lib/api";

export default function NavBar() {
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/api/me").then(setMe).catch(() => setMe(null));
  }, []);

  return (
    <nav className="nav">
      <span className="brand">📢 模型公告聚合</span>
      <Link className="link" href="/">公告时间线</Link>
      <Link className="link" href="/sources">源管理</Link>
      <Link className="link" href="/keywords">关键词</Link>
      <span className="spacer" />
      {me ? (
        <Link className="user" href="/settings">{me.email}</Link>
      ) : (
        <Link className="link" href="/login">登录</Link>
      )}
    </nav>
  );
}
```

`frontend/app/page.tsx`（临时占位）：

```tsx
export default function Home() {
  return <p>公告时间线（建设中）</p>;
}
```

- [ ] **Step 4: 验证构建与代理**

```bash
cd frontend && npm run build
```

Expected: 构建成功无 TypeScript 错误。

手动验收：后端 `uvicorn app.main:app --port 8000` 与前端 `npm run dev` 同时运行，浏览器打开 `http://localhost:3000`，导航栏正常显示、`/api/me` 请求返回 401（未登录，导航显示「登录」）。

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: 前端脚手架——Next.js、API 代理、全局布局与导航"
```

---

### Task 12: 公告时间线页（首页）

**Files:**
- Modify: `frontend/app/page.tsx`（替换占位实现）

**Interfaces:**
- Consumes: `GET /api/notices`、`GET /api/sources`、`lib/api.ts` 的类型与 `formatTime`
- Produces: `/` 页面——源筛选、只看命中/全部切换、标题搜索、分页

- [ ] **Step 1: 实现页面**

`frontend/app/page.tsx`：

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, formatTime, NoticeList, SourceItem } from "@/lib/api";

const PAGE_SIZE = 20;

export default function Home() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [matchedOnly, setMatchedOnly] = useState(true);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<NoticeList | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<SourceItem[]>("/api/sources").then(setSources).catch(() => {});
  }, []);

  const load = useCallback(() => {
    const params = new URLSearchParams({
      matched_only: String(matchedOnly),
      page: String(page),
      page_size: String(PAGE_SIZE),
    });
    if (sourceId) params.set("source_id", sourceId);
    if (search) params.set("q", search);
    api<NoticeList>(`/api/notices?${params}`)
      .then((d) => { setData(d); setError(""); })
      .catch((e) => setError(e.message));
  }, [sourceId, matchedOnly, search, page]);

  useEffect(load, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div>
      <div className="toolbar">
        <select value={sourceId} onChange={(e) => { setSourceId(e.target.value); setPage(1); }}>
          <option value="">全部源</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <label style={{ fontSize: 14 }}>
          <input
            type="checkbox"
            checked={matchedOnly}
            onChange={(e) => { setMatchedOnly(e.target.checked); setPage(1); }}
          />{" "}只看命中关键词
        </label>
        <input
          type="text"
          placeholder="搜索标题…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { setSearch(q); setPage(1); } }}
        />
        <button onClick={() => { setSearch(q); setPage(1); }}>搜索</button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {data?.items.map((n) => (
        <div className="card" key={n.id}>
          <div className="meta">
            <span className="tag">{n.source_name}</span>
            <span>{formatTime(n.published_at)}</span>
            {n.matched_keywords.map((k) => (
              <span className="kw" key={k}>{k}</span>
            ))}
          </div>
          <h3>
            <a href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
          </h3>
          {n.excerpt && <p className="excerpt">{n.excerpt}</p>}
        </div>
      ))}

      {data && data.items.length === 0 && <p style={{ color: "#6b7280" }}>暂无公告。</p>}

      <div className="pager">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
        <span>{page} / {totalPages}（共 {data?.total ?? 0} 条）</span>
        <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npm run build
```

Expected: 构建成功。

手动验收（前后端同时运行）：首页显示抓到的公告卡片（源标签、时间、命中关键词、外链）；切换源筛选/只看命中/搜索/翻页均正常。

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: 公告时间线页——筛选、搜索与分页"
```

---

### Task 13: 源管理页

**Files:**
- Create: `frontend/app/sources/page.tsx`

**Interfaces:**
- Consumes: `GET/POST/PATCH/DELETE /api/sources`、`POST /api/sources/{id}/fetch`
- Produces: `/sources` 页面——源列表（状态可视）、添加/编辑/删除/启停/立即抓取

- [ ] **Step 1: 实现页面**

`frontend/app/sources/page.tsx`：

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, formatTime, SourceItem } from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  aliyun_rss: "内置·阿里云RSS",
  volcengine: "内置·火山引擎",
  rss: "RSS",
  webpage: "网页链接",
};

export default function SourcesPage() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [type, setType] = useState("rss");
  const [url, setUrl] = useState("");

  const load = useCallback(() => {
    api<SourceItem[]>("/api/sources").then(setSources).catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    try {
      setError("");
      await fn();
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const add = () =>
    run(async () => {
      await api("/api/sources", {
        method: "POST",
        body: JSON.stringify({ name, type, url }),
      });
      setName(""); setUrl("");
    });

  const toggle = (s: SourceItem) =>
    run(() => api(`/api/sources/${s.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !s.enabled }),
    }));

  const remove = (s: SourceItem) => {
    if (!confirm(`确认删除源「${s.name}」？其下所有公告也会被删除。`)) return;
    run(() => api(`/api/sources/${s.id}`, { method: "DELETE" }));
  };

  const fetchNow = async (s: SourceItem) => {
    setBusy(s.id);
    await run(async () => {
      const r = await api<{ new_items: number }>(`/api/sources/${s.id}/fetch`, { method: "POST" });
      alert(`「${s.name}」抓取完成，新增 ${r.new_items} 条`);
    });
    setBusy(null);
  };

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>源管理</h2>
      {error && <div className="error-box">{error}（管理操作需要先登录）</div>}

      <div className="card">
        <div className="form-row">
          <input type="text" placeholder="源名称" value={name} onChange={(e) => setName(e.target.value)} />
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="rss">RSS 订阅</option>
            <option value="webpage">网页链接</option>
          </select>
          <input type="text" placeholder="https://…" style={{ flex: 1, minWidth: 240 }}
                 value={url} onChange={(e) => setUrl(e.target.value)} />
          <button className="primary" onClick={add} disabled={!name || !url}>添加源</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>名称</th><th>类型</th><th>最近抓取</th><th>状态</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id} style={{ opacity: s.enabled ? 1 : 0.5 }}>
              <td>
                {s.name}
                <div style={{ fontSize: 12, color: "#9ca3af", wordBreak: "break-all" }}>{s.url}</div>
              </td>
              <td>{TYPE_LABELS[s.type] ?? s.type}</td>
              <td>{formatTime(s.last_fetch_at)}</td>
              <td>
                {s.last_fetch_status === "ok" && <span className="status-ok">正常</span>}
                {s.last_fetch_status === "error" && (
                  <span className="status-error" title={s.last_error ?? ""}>
                    失败：{(s.last_error ?? "").slice(0, 80)}
                  </span>
                )}
                {!s.last_fetch_status && <span style={{ color: "#9ca3af" }}>未抓取</span>}
              </td>
              <td>
                <div className="form-row">
                  <button onClick={() => fetchNow(s)} disabled={busy === s.id}>
                    {busy === s.id ? "抓取中…" : "立即抓取"}
                  </button>
                  <button onClick={() => toggle(s)}>{s.enabled ? "停用" : "启用"}</button>
                  {!s.is_builtin && (
                    <button className="danger" onClick={() => remove(s)}>删除</button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: 验证**

```bash
cd frontend && npm run build
```

Expected: 构建成功。

手动验收：未登录时管理操作报「未登录」提示；登录后可添加 RSS/网页源、启停、删除自定义源（内置源无删除按钮）、「立即抓取」返回新增条数，失败源红字显示错误信息。

- [ ] **Step 3: Commit**

```bash
git add frontend/app/sources/
git commit -m "feat: 源管理页——增删启停、抓取状态可视与手动抓取"
```

---

### Task 14: 关键词管理页 + 登录页 + 个人设置页

**Files:**
- Create: `frontend/app/keywords/page.tsx`、`frontend/app/login/page.tsx`、`frontend/app/settings/page.tsx`

**Interfaces:**
- Consumes: `GET/POST/PATCH/DELETE /api/keywords`、`POST /api/auth/request-code`、`POST /api/auth/verify`、`POST /api/auth/logout`、`GET/PATCH /api/me`、`GET /api/users`
- Produces: `/keywords`、`/login`、`/settings` 三个页面

- [ ] **Step 1: 实现关键词管理页**

`frontend/app/keywords/page.tsx`：

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, KeywordItem } from "@/lib/api";

export default function KeywordsPage() {
  const [keywords, setKeywords] = useState<KeywordItem[]>([]);
  const [word, setWord] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<KeywordItem[]>("/api/keywords").then(setKeywords).catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    try {
      setError("");
      await fn();
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const add = () =>
    run(async () => {
      await api("/api/keywords", { method: "POST", body: JSON.stringify({ word }) });
      setWord("");
    });

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>关键词管理</h2>
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 16 }}>
        公告标题或正文命中任一启用的关键词（不区分大小写）即触发邮件提醒。
      </p>
      {error && <div className="error-box">{error}（管理操作需要先登录）</div>}

      <div className="card">
        <div className="form-row">
          <input type="text" placeholder="新关键词，如：下线" value={word}
                 onChange={(e) => setWord(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && word) add(); }} />
          <button className="primary" onClick={add} disabled={!word}>添加</button>
        </div>
      </div>

      <table>
        <thead>
          <tr><th>关键词</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          {keywords.map((k) => (
            <tr key={k.id} style={{ opacity: k.enabled ? 1 : 0.5 }}>
              <td>{k.word}</td>
              <td>{k.enabled ? <span className="status-ok">启用</span> : "停用"}</td>
              <td>
                <div className="form-row">
                  <button onClick={() => run(() => api(`/api/keywords/${k.id}`, {
                    method: "PATCH", body: JSON.stringify({ enabled: !k.enabled }),
                  }))}>{k.enabled ? "停用" : "启用"}</button>
                  <button className="danger" onClick={() => run(() =>
                    api(`/api/keywords/${k.id}`, { method: "DELETE" })
                  )}>删除</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: 实现登录页**

`frontend/app/login/page.tsx`：

```tsx
"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"email" | "code">("email");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const requestCode = async () => {
    try {
      setError("");
      await api("/api/auth/request-code", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setStage("code");
      setMessage(`验证码已发送到 ${email}，10 分钟内有效。`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const verify = async () => {
    try {
      setError("");
      await api("/api/auth/verify", {
        method: "POST",
        body: JSON.stringify({ email, code }),
      });
      window.location.href = "/";  // 整页刷新，让 NavBar 重新拉 /api/me
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="card" style={{ maxWidth: 420, margin: "48px auto", padding: 32 }}>
      <h2 style={{ marginBottom: 8 }}>邮箱登录</h2>
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 20 }}>
        登录即订阅：新公告提醒会发送到这个邮箱。
      </p>
      {error && <div className="error-box">{error}</div>}
      {message && <p style={{ fontSize: 13, color: "#16a34a", marginBottom: 12 }}>{message}</p>}

      {stage === "email" ? (
        <div className="form-row">
          <input type="email" placeholder="you@qq.com" style={{ flex: 1 }} value={email}
                 onChange={(e) => setEmail(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && email) requestCode(); }} />
          <button className="primary" onClick={requestCode} disabled={!email}>发送验证码</button>
        </div>
      ) : (
        <div className="form-row">
          <input type="text" placeholder="6 位验证码" style={{ flex: 1 }} value={code}
                 maxLength={6}
                 onChange={(e) => setCode(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && code.length === 6) verify(); }} />
          <button className="primary" onClick={verify} disabled={code.length !== 6}>登录</button>
          <button onClick={() => { setStage("email"); setMessage(""); }}>返回</button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: 实现个人设置页**

`frontend/app/settings/page.tsx`：

```tsx
"use client";

import { useEffect, useState } from "react";
import { api, formatTime, Me } from "@/lib/api";

interface Member {
  email: string;
  notify_enabled: boolean;
  last_login_at: string | null;
}

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Me>("/api/me")
      .then((m) => {
        setMe(m);
        return api<Member[]>("/api/users").then(setMembers);
      })
      .catch(() => { window.location.href = "/login"; });
  }, []);

  const toggleNotify = async () => {
    if (!me) return;
    try {
      const updated = await api<Me>("/api/me", {
        method: "PATCH",
        body: JSON.stringify({ notify_enabled: !me.notify_enabled }),
      });
      setMe(updated);
      setMembers((ms) => ms.map((m) =>
        m.email === updated.email ? { ...m, notify_enabled: updated.notify_enabled } : m
      ));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" });
    window.location.href = "/";
  };

  if (!me) return <p>加载中…</p>;

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>个人设置</h2>
      {error && <div className="error-box">{error}</div>}

      <div className="card">
        <div className="form-row" style={{ justifyContent: "space-between" }}>
          <div>
            <div style={{ fontWeight: 600 }}>{me.email}</div>
            <div style={{ fontSize: 13, color: "#6b7280", marginTop: 4 }}>
              邮件提醒：{me.notify_enabled ? "已开启" : "已关闭"}
            </div>
          </div>
          <div className="form-row">
            <button onClick={toggleNotify}>
              {me.notify_enabled ? "关闭提醒" : "开启提醒"}
            </button>
            <button className="danger" onClick={logout}>退出登录</button>
          </div>
        </div>
      </div>

      <h3 style={{ margin: "20px 0 12px" }}>成员列表</h3>
      <table>
        <thead>
          <tr><th>邮箱</th><th>提醒</th><th>最近登录</th></tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.email}>
              <td>{m.email}</td>
              <td>{m.notify_enabled ? <span className="status-ok">开启</span> : "关闭"}</td>
              <td>{formatTime(m.last_login_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: 验证**

```bash
cd frontend && npm run build
```

Expected: 构建成功。

手动验收（需配置真实 SMTP 环境变量，或临时看后端日志/数据库取验证码）：
1. `/login` 输入邮箱 → 收到验证码邮件 → 登录成功跳首页，导航栏显示邮箱；
2. `/keywords` 可增删启停关键词；
3. `/settings` 可切换提醒开关、看到成员列表、退出登录后跳回首页。

- [ ] **Step 5: Commit**

```bash
git add frontend/app/
git commit -m "feat: 关键词管理、邮箱验证码登录与个人设置页"
```

---

### Task 15: Docker 打包、环境变量样例与 README

**Files:**
- Create: `backend/Dockerfile`、`frontend/Dockerfile`、`docker-compose.yml`、`.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: 前面全部任务的产物
- Produces: `docker-compose up -d` 一键部署；`.env.example` 配置模板

- [ ] **Step 1: 写 backend Dockerfile**

`backend/Dockerfile`：

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: 写 frontend Dockerfile**

`frontend/Dockerfile`（standalone 产物；`BACKEND_URL` 在构建时烧入 rewrites，指向 compose 服务名）：

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ENV BACKEND_URL=http://backend:8000
RUN npm run build

FROM node:20-alpine

WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
ENV HOSTNAME=0.0.0.0 PORT=3000
CMD ["node", "server.js"]
```

- [ ] **Step 3: 写 docker-compose 与 .env.example**

`docker-compose.yml`：

```yaml
services:
  backend:
    build: ./backend
    env_file: .env
    environment:
      DATABASE_URL: sqlite:///./data/notice.db
    volumes:
      - ./data:/app/data
    ports:
      - "8000:8000"
    restart: unless-stopped

  frontend:
    build: ./frontend
    depends_on:
      - backend
    ports:
      - "3000:3000"
    restart: unless-stopped
```

`.env.example`：

```env
# QQ 邮箱 SMTP（在 QQ 邮箱「设置-账号」开启 SMTP 服务并生成授权码）
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your-account@qq.com
SMTP_AUTH_CODE=your-smtp-auth-code

# 会话签名密钥（改成随机长字符串）
SECRET_KEY=please-change-me-to-a-random-string

# 抓取轮询间隔（分钟）
FETCH_INTERVAL_MINUTES=30
```

- [ ] **Step 4: 更新 README**

`README.md` 全文替换为：

````markdown
# notice · 模型公告聚合与邮件提醒平台

聚合各厂商大模型上下线公告（内置阿里云、火山引擎，支持自定义 RSS / 网页源），
命中关键词的新公告**立即合并发送 QQ 邮箱提醒**，网页端提供公告时间线与管理界面。

## 快速开始（Docker）

```bash
cp .env.example .env      # 填入 QQ 邮箱 SMTP 授权码和随机 SECRET_KEY
docker-compose up -d
```

- 网页端：http://localhost:3000 （邮箱验证码登录，登录即订阅提醒）
- 后端 API：http://localhost:8000/docs
- 数据持久化在 `./data/notice.db`（SQLite）

## 本地开发

后端（Python 3.11+）：

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Linux/Mac: .venv/bin/pip
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

前端（Node 20+）：

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000，/api 自动代理到 :8000
```

测试：

```bash
cd backend && python -m pytest tests -v
```

## 设计文档

- 规格：`docs/superpowers/specs/2026-07-10-model-notice-aggregator-design.md`
- 实现计划：`docs/superpowers/plans/2026-07-10-model-notice-aggregator.md`
````

- [ ] **Step 5: 验证 Docker 构建与运行**

```bash
cp .env.example .env    # 若尚未创建（可先不填真实授权码）
docker-compose build
docker-compose up -d
```

验证：

```bash
curl http://localhost:8000/api/health     # {"status":"ok"}
curl http://localhost:3000                # 返回 HTML
docker-compose logs backend | tail -20    # 可见调度器启动与首轮抓取日志
docker-compose down
```

Expected: 两个镜像构建成功，服务可访问；未配置真实 SMTP 时基线抓取正常入库、无邮件外发。

- [ ] **Step 6: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile docker-compose.yml .env.example README.md
git commit -m "chore: Docker Compose 打包、环境变量样例与 README"
```

---

## 总验收清单（全部任务完成后走一遍）

1. `cd backend && python -m pytest tests -v` → 全部通过（约 30 个测试）。
2. 本地起前后端，配置真实 QQ SMTP：登录一个真实 QQ 邮箱账号 → 收到验证码 → 登录成功。
3. 等首轮抓取（15 秒）：首页出现阿里云 + 火山的基线公告；**无邮件轰炸**（基线不发信）。
4. 源管理页添加一个自定义 RSS 源（如 `https://cn.aliyun.com/rss/notice/zh.xml` 再加一次也行）→「立即抓取」→ 条目入库为基线。
5. 制造一次真实通知：临时把某关键词删掉再加回（或手动把某条 notice 的 `notified_at`、`is_baseline` 清掉）→ 下一轮触发合并邮件 → QQ 邮箱收到「【模型公告提醒】…」。
6. 源管理页把一个源的 URL 改成无效地址 →「立即抓取」→ 状态列红色显示错误信息。
7. `docker-compose up -d` 全流程可用（步骤 2-6 在容器环境重复抽查 2-3 项）。

