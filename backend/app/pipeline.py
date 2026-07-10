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
