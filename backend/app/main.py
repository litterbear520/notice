from fastapi import FastAPI

from .routers import auth_users

app = FastAPI(title="模型公告聚合平台")
app.include_router(auth_users.router)
