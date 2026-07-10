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
