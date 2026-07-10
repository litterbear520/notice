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
