# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

模型公告聚合与邮件提醒平台：后端定时抓取各厂商公告（内置阿里云 RSS、火山引擎文档站，支持自定义 RSS/网页源），命中关键词的新公告合并成一封邮件发给订阅成员。FastAPI + SQLite + APScheduler（backend/）、Next.js 14 App Router（frontend/）。

## 常用命令

```bash
# 后端（虚拟环境在 backend/.venv）
cd backend
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000   # 开发服务
./.venv/bin/python -m pytest tests -q                             # 全部测试
./.venv/bin/python -m pytest tests/test_auth.py -q                # 单文件
./.venv/bin/python -m pytest tests/test_auth.py::test_verify_wrong_code -q  # 单测试
./.venv/bin/python scripts/send_test_email.py [收件邮箱]           # SMTP 冒烟（先做网络预检）

# 前端
cd frontend
npm run dev     # http://localhost:3000，/api 由 next.config.js rewrites 代理到 :8000
npm run build   # 生产构建（同时做类型检查）
npx tsc --noEmit  # 仅类型检查（最快）
```

本地需要 `.env`（从 `.env.example` 复制），否则发信功能报错但其余可用。

## 架构

### 后端数据流（pipeline.py 是核心）

`scheduler.py` 在 uvicorn 进程内起 APScheduler，每 `FETCH_INTERVAL_MINUTES`（默认 30）分钟跑一轮 `run_round`：

1. `fetch_source`：对每个启用源调用 `adapters.fetch_items(type, url)` → 按 `(source_id, url)` 去重入库 → `matching.find_matches`（大小写不敏感子串、OR 语义）标记命中 → 更新源的 `last_fetch_status`
2. `send_pending`：把 `matched=True, notified_at=None, is_baseline=False` 的公告合并为一封邮件群发；发送失败不标记，下一轮自动重试

**基线语义**：源的首次抓取所有条目标 `is_baseline=True`，永不触发邮件——避免新增源时轰炸历史公告。

**约束：必须单 worker 部署**。调度器和限流器都是进程内状态，`uvicorn --workers N` 会导致重复抓取、重复发邮件、限流失效。

### 适配器（backend/app/adapters/）

- `rss.py`：feedparser，`aliyun_rss` 与自定义 `rss` 共用
- `webpage.py`：抓取页面全部同域链接当条目（不执行 JS，SPA 页面抓不到）
- `volcengine.py`：解析文档页内嵌的 `window._ROUTER_DATA` JSON。盯守 3 个"原地更新"的文档（`WATCH_DOC_IDS`），用 `UpdatedTime` 合成带时间戳锚点的 URL 实现"更新即新条目"；同时扫目录树发现新增文档（注意：新增文档只有标题没有正文和时间）。**该站点 SSR 间歇性以 HTTP 200 返回不含 `_ROUTER_DATA` 的错误壳页面**（实测故障率可达 50%），因此有 4 次尝试 + 递增退避的重试逻辑，勿删

### 认证与限流（auth.py）

邮箱验证码登录（6 位、10 分钟、一次性），会话是 itsdangerous 签名 cookie（30 天）。三个进程内滑动窗口限流器：单邮箱 5 次/时、全站 30 次/时、验证尝试 30 次/10 分钟——公网部署的防滥用底线，测试通过 conftest 的 autouse fixture 在用例间重置。

**权限模型**：管理员由 `ADMIN_EMAILS` 环境变量决定（逗号分隔，默认 `970219247@qq.com`），不在数据库里。`get_current_admin` 保护源/关键词的增删改与 `/api/users`；普通登录用户只能看公告、改自己的提醒开关。`/api/me` 返回 `is_admin`，前端据此显隐管理导航并在管理页做跳转守卫。测试环境的管理员是 `admin@qq.com`（conftest 设置）。

### 数据库

SQLAlchemy `create_all`，**没有迁移工具**：改 `models.py` 表结构不会自动同步已有库，需要手写迁移/ALTER，改表前先提醒用户。时间约定：库里全是 naive UTC（`datetime.utcnow()`），邮件展示时 +8 小时标注北京时间。

### 前端

- 无 UI 框架，纯 CSS 设计令牌体系在 `app/globals.css`：`:root` 定义 cream+coral 浅色令牌，`[data-theme="dark"]` 整套覆盖为暖黑。色彩规范参考 `frontend/DESIGN.md`（cream 画布 / coral 主色；字体已按用户要求改为系统字体栈，忽略该文档的衬线标题要求）
- 主题切换：`layout.tsx` 里的内联脚本在首帧前读 localStorage/系统偏好设置 `data-theme`，`ThemeToggle` 组件负责切换
- 时间线只展示标题不展示正文摘要（用户明确要求）；注意后端存的 `content` 含 Markdown/HTML 残留，如需展示正文须先清洗
- `BACKEND_URL` 在 **构建期**烤进 Next 产物（rewrites），运行时改环境变量无效

### 测试约定（backend/tests/）

- `sent_emails` fixture 通过 monkeypatch `app.mailer.send_email` 截获外发邮件——业务代码必须用 `from .. import mailer; mailer.send_email(...)` 的形式调用，直接 `from ..mailer import send_email` 会绕过截获
- 适配器测试用 `tests/fixtures/` 里的真实页面快照，不打网络

## 部署

push 到 main 自动触发 `.github/workflows/deploy.yml`：测试 → buildx 构建 amd64 镜像推 GHCR → SSH 到服务器执行 `docker compose -f docker-compose.prod.yml pull && up -d`。生产环境在服务器 `/opt/notice/`（compose 文件 + `.env`），前端映射 80 端口，后端不暴露公网。

- **改服务器 `.env` 后必须 `docker compose up -d --force-recreate backend`**——`restart` 不会重新读取 env_file，这个坑踩过
- 改 `docker-compose.prod.yml` 需手动拷到服务器；改 `models.py` 表结构需手动迁移；其余改动 push 即上线
- 生产发件人用 Gmail SMTP：QQ 邮箱风控疑似拒绝海外服务器 IP 的 SMTP AUTH（连接在 AUTH 阶段被直接掐断，不返回 535）

## 设计文档

- 原始规格：`docs/superpowers/specs/2026-07-10-model-notice-aggregator-design.md`
- 实现计划：`docs/superpowers/plans/2026-07-10-model-notice-aggregator.md`
