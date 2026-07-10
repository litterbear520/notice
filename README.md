# notice · 模型公告聚合与邮件提醒平台

聚合各厂商大模型上下线公告（内置阿里云、火山引擎，支持自定义 RSS / 网页源），
命中关键词的新公告**立即合并发送 QQ 邮箱提醒**，网页端提供公告时间线与管理界面。

## 快速开始（Docker）

```bash
cp .env.example .env      # 填入 QQ 邮箱 SMTP 授权码和随机 SECRET_KEY
docker compose up -d
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
