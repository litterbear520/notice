from fastapi import FastAPI

from .routers import auth_users, keywords, notices, sources

app = FastAPI(title="模型公告聚合平台")
for r in (notices.router, sources.router, keywords.router, auth_users.router):
    app.include_router(r)
