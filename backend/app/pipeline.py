import json
import logging
from datetime import datetime, timedelta
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import mailer
from .adapters import AdapterError, fetch_items
from .config import settings
from .matching import find_matches
from .models import Keyword, Notice, Source, User

logger = logging.getLogger(__name__)

# 各源的连续失败轮数（进程内状态，依赖单 worker 部署；重启后重新累计）
_consecutive_failures: dict[int, int] = {}


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
    try:
        for item in items:
            url = item.url[:1000]
            if url in existing:
                continue
            existing.add(url)
            matches = find_matches(item.title, item.content, words)
            db.add(Notice(
                source_id=source.id,
                title=item.title[:500],
                url=url,
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
    except Exception as e:
        db.rollback()
        source.last_fetch_at = datetime.utcnow()
        source.last_fetch_status = "error"
        source.last_error = str(e)[:1000]
        db.commit()
        logger.warning("源「%s」抓取失败: %s", source.name, e)
        return 0
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


def _track_source_health(source: Source) -> None:
    """连续失败达到阈值时给管理员发一次告警，恢复后计数清零。"""
    if source.last_fetch_status == "error":
        count = _consecutive_failures.get(source.id, 0) + 1
        _consecutive_failures[source.id] = count
        if count == settings.source_alert_failures:
            _send_source_alert(source, count)
    else:
        _consecutive_failures.pop(source.id, None)


def _send_source_alert(source: Source, failures: int) -> None:
    admins = sorted(settings.admin_email_set)
    if not admins:
        return
    beijing = datetime.utcnow() + timedelta(hours=8)
    subject = f"【公告聚合告警】源「{source.name}」连续 {failures} 轮抓取失败"
    html = (
        f"<p>源「{escape(source.name)}」已连续 {failures} 轮抓取失败，"
        f"期间该源的新公告会延迟或漏检，请尽快排查。</p>"
        f"<p>源地址：{escape(source.url)}<br>"
        f"最近错误：{escape(source.last_error or '未知')}<br>"
        f"时间：{beijing:%Y-%m-%d %H:%M}（北京时间）</p>"
        f"<p>可到「源管理」页手动抓取验证；常见原因是站点临时故障或页面改版。"
        f"恢复后计数自动清零，再次故障会重新告警。</p>"
    )
    try:
        mailer.send_email(admins, subject, html)
        logger.info("已向管理员发送源告警: %s", source.name)
    except Exception as e:
        logger.error("源告警邮件发送失败: %s", e)


def run_round(db: Session) -> dict:
    """一轮完整流水线：抓取所有启用源 + 发送待发通知。"""
    sources = list(db.scalars(select(Source).where(Source.enabled == True)))  # noqa: E712
    total_new = 0
    for s in sources:
        total_new += fetch_source(db, s)
        _track_source_health(s)
    notified = send_pending(db)
    logger.info("本轮完成：%d 个源，新条目 %d，通知 %d 条", len(sources), total_new, notified)
    return {"sources": len(sources), "new_items": total_new, "notified": notified}
