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
