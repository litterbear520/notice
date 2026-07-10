# 模型公告聚合与邮件提醒平台 · 设计文档

日期：2026-07-10
状态：已与需求方确认

## 1. 背景与目标

团队曾因未及时得知阿里云百炼平台的模型下线公告（如 <https://cn.aliyun.com/notice/118331>），在产品即将上线时才从客服处获知所依赖的模型将停服，险些造成损失。各厂商的模型上下线公告分散在各自的公告页/文档站，没人主动通知用户。

**目标**：做一个内部使用的 Web 平台，自动聚合各厂商模型上下线相关公告，发现新公告后立即通过 QQ 邮箱（SMTP）提醒团队成员，并在网页上提供可检索的公告时间线。

参考产品：aihot.virxact.com（AI 信息聚合平台），但本项目范围更小、更聚焦。

## 2. 范围

### MVP 包含

- 内置两个开箱即用的源：
  - **阿里云公告 RSS**：`https://cn.aliyun.com/rss/notice/zh.xml`（标准 RSS，含 title / link / content:encoded / pubDate；注意 `www.aliyun.com` 会 302 到 `cn.aliyun.com`，直接使用 cn 域名）
  - **火山引擎产品公告**：`https://docs.volcengine.com/docs/82379/1159176?lang=zh`（无 RSS。已实测验证：公告文档树和文档正文均内嵌在页面静态 HTML 的 `window._ROUTER_DATA` JSON 中，纯 httpx 可抓取，无需无头浏览器。注意其公告是「一个文档原地追加更新」模式，需专用适配器做**内容更新检测**，详见 §5）
- 自定义源：支持添加 **RSS/Atom 链接** 和 **普通网页链接** 两种类型
- 可配置的**关键词规则**筛选（命中才提醒）
- **发现新公告立即发邮件**（定时轮询，同轮多条合并为一封）
- **邮箱验证码登录**（无密码），登录邮箱即通知邮箱
- 前端页面：公告时间线、源管理、关键词管理、登录/个人设置
- 本地可直接运行，支持 Docker Compose 打包部署

### MVP 不包含（二期扩展点）

- 每日汇总邮件
- CSS 选择器配置式抓取、LLM 智能提取
- 管理员/普通成员角色区分
- 站内消息、企业微信/钉钉等其他通知渠道
- 公告正文全文抓取（webpage 类型源只有标题+链接，无正文）

## 3. 架构

单体后端 + 独立前端，两个服务：

```
notice/
├── backend/            # FastAPI，Python 3.11+
│   ├── 定时调度        # APScheduler（进程内），默认每 30 分钟轮询
│   ├── 源适配器        # aliyun_rss / volcengine / rss / webpage
│   ├── REST API        # 公告、源、关键词、认证、个人设置
│   └── 邮件发送        # aiosmtplib → QQ 邮箱 SMTP
├── frontend/           # Next.js (App Router) + React + TypeScript
├── docker-compose.yml  # backend(8000) + frontend(3000)
├── data/               # SQLite 数据库文件（挂载卷）
└── .env.example
```

后端依赖：`fastapi`、`uvicorn`、`sqlalchemy`、`apscheduler`、`feedparser`、`httpx`、`beautifulsoup4`、`aiosmtplib`、`itsdangerous`（签发登录 token）、`pytest`（测试）。

前后端集成：前端通过 Next.js rewrites 把 `/api/*` 代理到后端（浏览器视角同源），HttpOnly Cookie 直接生效，无需处理 CORS 与跨域 Cookie。

设计取舍：内部小团队工具，不引入消息队列、独立 worker、Redis；SQLite 单文件即数据库。抓取任务使用异步 + 超时控制，避免阻塞 API。

## 4. 数据模型（SQLite，5 张表）

### sources（源）

| 字段 | 说明 |
|---|---|
| id | 主键 |
| name | 显示名称，如「阿里云公告」 |
| type | `aliyun_rss` / `volcengine` / `rss` / `webpage` |
| url | 抓取地址 |
| enabled | 是否启用 |
| last_fetch_at | 最近抓取时间 |
| last_fetch_status | `ok` / `error` / 未抓取 |
| last_error | 最近一次错误信息（成功时清空） |
| created_at | 创建时间 |

内置的阿里云、火山引擎两个源作为**种子数据**在数据库初始化时预置（type 分别为 `aliyun_rss`、`volcengine`），内置源可停用但不可删除。

### notices（公告条目）

| 字段 | 说明 |
|---|---|
| id | 主键 |
| source_id | 所属源，外键 |
| title | 标题 |
| url | 原文链接，**(source_id, url) 唯一**——既是去重键，也是 webpage 链接差异检测的「已见过」判断依据。volcengine 源的「文档更新」类条目使用合成锚点形式 `文档URL#u<更新时间>` 以区分同一文档的多次更新（详见 §5） |
| content | 正文/摘要（纯文本，截断存储，上限 5000 字符；webpage 类型为空） |
| published_at | 发布时间（RSS 取 pubDate；取不到的用抓取时间） |
| fetched_at | 入库时间 |
| matched | 是否命中关键词 |
| matched_keywords | 命中的关键词列表（JSON，供前端高亮） |
| notified_at | 邮件发送成功时间；`matched=true 且 notified_at 为空且非基线` 即待发送 |
| is_baseline | 是否为基线导入（源首次抓取的存量条目，不发邮件） |

### keywords（关键词）

| 字段 | 说明 |
|---|---|
| id | 主键 |
| word | 关键词 |
| enabled | 是否启用 |

匹配规则：对「标题 + 正文」做**忽略大小写的子串匹配**，命中**任一**启用关键词即 `matched=true`（OR 语义）。

预置默认关键词：`模型`、`下线`、`停售`、`停止服务`、`废弃`、`到期`、`百炼`、`qwen`、`豆包`、`doubao`、`deprecat`（英文词干，覆盖 deprecated/deprecation）。

### users（成员）

| 字段 | 说明 |
|---|---|
| id | 主键 |
| email | 邮箱，唯一 |
| notify_enabled | 是否接收邮件提醒，默认 true |
| created_at | 创建时间（首次登录自动创建） |
| last_login_at | 最近登录时间 |

### login_codes（登录验证码）

| 字段 | 说明 |
|---|---|
| id | 主键 |
| email | 邮箱 |
| code | 6 位数字验证码 |
| expires_at | 过期时间（生成后 10 分钟） |
| used | 是否已使用 |

## 5. 源适配器

所有适配器实现统一接口：输入源配置，输出条目列表 `[(title, url, content, published_at)]`。

- **aliyun_rss**：`feedparser` 解析官方 RSS，正文取 `content:encoded` 并转纯文本。
- **volcengine**：专用抓取器。**关键背景（已实测验证）**：火山的「模型下线公告」等是**单个文档原地追加更新**（如新批次下线直接追加进 `docs/82379/1350667`），不是每条公告一个新链接，因此不能用链接差异检测，必须做内容更新检测。数据来源：文档页静态 HTML 中的 `window._ROUTER_DATA` JSON（Modern.js SSR 数据），用正则提取 `window._ROUTER_DATA = {...}` 后 `json.loads`，其中含：
  - `loaderData.*.docListMap`：文档树（文档 ID → 标题），用于发现**新增**的公告文档；
  - 当前文档正文（Quill Delta 格式的 `{"insert": ...}` 操作序列，拼接 insert 字段即得纯文本）及文档最近更新时间。

  监控逻辑（两条腿）：
  1. **内容更新检测**：监控固定的三个公告文档——模型下线公告（`1350667`）、模型发布公告（`1159178`）、产品更新公告（`1159177`）。逐个抓取文档页，提取正文纯文本和最近更新时间；产出条目 `url = 文档URL#u<最近更新时间>`（利用 (source_id, url) 唯一键天然去重：更新时间没变则 url 已存在被跳过，变了即新条目触发通知）。title 如「模型下线公告 已更新」，content 为正文纯文本（截断），published_at 为该更新时间。
  2. **新文档检测**：从目录页的 `docListMap` 中发现产品公告分类下新增的文档（如年度归档、一次性公告），每个新文档 ID 产出一个条目（url 为文档 URL，title 为文档标题）。

  抓取时设置浏览器 UA（站点有反爬检测，实测带常见浏览器 UA 的 httpx 请求可正常拿到完整 HTML）。若 `_ROUTER_DATA` 提取或解析失败，记该源抓取 error（提示可能改版）。
- **rss**（自定义）：标准 RSS/Atom 解析，逻辑同 aliyun_rss。
- **webpage**（自定义，链接差异检测）：
  1. `httpx` 抓取页面 HTML（超时 30s，UA 伪装为常见浏览器）；
  2. `BeautifulSoup` 提取所有 `<a>` 标签的 `href` + 链接文本；
  3. 相对链接转绝对链接；过滤噪声：无文本或文本长度 < 6 的链接、`#` 锚点、`javascript:` 链接、站外链接（固定规则：只保留与源 URL 同域名的链接，不做成配置项）；
  4. 与 notices 表中该源已有 url 对比，**新出现的链接**即新条目（title=链接文本，content 为空）。

页面改版容错：webpage 源提取到 0 条链接不算错误（记为正常抓取、0 新增）；仅 HTTP 请求失败/超时才记 `error`。

## 6. 抓取 → 筛选 → 通知流水线

APScheduler 每 `FETCH_INTERVAL_MINUTES`（默认 30）分钟执行一轮，对所有启用的源依次：

1. **抓取**：调用对应适配器。单个源失败：记录 `last_fetch_status=error` 和 `last_error`，继续下一个源。
2. **去重入库**：条目 url 已存在 → 跳过；新条目 → 入库。**该源首次抓取**（notices 表中无该源任何记录）时，本轮全部条目标记 `is_baseline=true`。
3. **筛选**：新条目跑关键词匹配，写入 `matched` 和 `matched_keywords`。
4. **通知**：收集全库「`matched=true` 且 `notified_at` 为空且 `is_baseline=false`」的条目（含上轮发送失败遗留的），**合并为一封邮件**，群发给所有 `notify_enabled=true` 的成员。发送成功后统一写 `notified_at`。收件人为空或无待发条目则跳过。
5. **状态更新**：源的 `last_fetch_at` / `last_fetch_status`。

邮件内容（HTML）：每条公告一个区块——源名称、标题（链接到原文）、发布时间、命中关键词、正文摘要（前 300 字符）。主题如：`【模型公告提醒】阿里云公告等 2 条新公告`。

失败重试：邮件发送失败不写 `notified_at`，下一轮自动重新纳入待发集合，天然幂等；不做轮内重试。

手动触发：源管理页「立即抓取」按钮调用 API 对单个源同步执行上述 1–5 步（复用同一段流水线代码），用于添加源后即时验证。

## 7. 登录认证（邮箱验证码，无密码）

1. `POST /api/auth/request-code`：输入邮箱 → 生成 6 位验证码存 login_codes（10 分钟有效），经同一 SMTP 通道发送。**限流：同一邮箱 60 秒内只能请求一次**（查该邮箱最近一条 code 的创建时间）。
2. `POST /api/auth/verify`：校验邮箱+验证码（未过期、未使用）→ 标记已用；users 无此邮箱则自动创建（**登录即订阅**）→ 用 `itsdangerous` 签发 token，写入 **HttpOnly Cookie**，30 天有效。
3. 鉴权：写操作（源、关键词的增删改、个人设置、手动抓取）要求登录；读操作（公告列表、源列表）不要求。**不区分角色**，所有登录成员权限一致。
4. `SECRET_KEY` 走环境变量。

## 8. REST API 概览

| 方法 & 路径 | 说明 | 鉴权 |
|---|---|---|
| GET /api/notices | 公告列表：分页、`source_id` 筛选、`matched_only`（默认 true）、`q` 标题搜索 | 否 |
| GET /api/sources | 源列表（含抓取状态） | 否 |
| POST /api/sources | 添加自定义源（type ∈ rss/webpage） | 是 |
| PATCH /api/sources/{id} | 编辑名称/URL/启用开关 | 是 |
| DELETE /api/sources/{id} | 删除自定义源（内置源拒绝删除；级联删除其 notices） | 是 |
| POST /api/sources/{id}/fetch | 立即抓取该源 | 是 |
| GET /api/keywords | 关键词列表 | 否 |
| POST /api/keywords | 添加关键词 | 是 |
| PATCH /api/keywords/{id} | 启用/停用 | 是 |
| DELETE /api/keywords/{id} | 删除 | 是 |
| POST /api/auth/request-code | 请求登录验证码 | 否 |
| POST /api/auth/verify | 校验验证码、签发 Cookie | 否 |
| POST /api/auth/logout | 退出登录 | 是 |
| GET /api/me | 当前登录成员信息 | 是 |
| PATCH /api/me | 切换「接收邮件提醒」开关 | 是 |
| GET /api/users | 成员列表（邮箱、提醒开关状态） | 是 |

## 9. 前端页面（Next.js App Router，4 个页面）

1. **`/` 公告时间线**：时间倒序卡片流——源名称标签、标题、发布时间、命中关键词高亮、原文外链。顶部工具栏：源筛选下拉、「只看命中 / 看全部」切换、标题搜索框。分页加载。未登录可浏览。
2. **`/sources` 源管理**：源列表表格（名称、类型、URL、启用开关、最近抓取时间、状态——失败的红色标出并展示错误信息）、「添加源」对话框（类型选 RSS/网页链接 + URL + 名称）、编辑/删除、「立即抓取」按钮。
3. **`/keywords` 关键词管理**：关键词列表 + 添加 + 启用开关 + 删除。
4. **`/login` 登录页 与 `/settings` 个人设置**：邮箱 → 验证码 → 登录；设置页含「接收邮件提醒」开关和成员列表。

全局：导航栏显示登录状态；未登录点写操作跳登录页。UI 简洁即可，不追求视觉设计（内部工具）。

## 10. 错误处理

- **抓取失败**：写入源的 `last_fetch_status` / `last_error`，源管理页红色可见。**连续失败不自动禁用源**——自动禁用等于静默漏报，与本项目「不能漏掉公告」的初衷冲突，靠页面可见性交给人处理。
- **邮件发送失败**：条目保留待发状态下一轮自动重试；SMTP 异常写后端日志（ERROR 级）。
- **验证码邮件失败**：接口返回明确错误（如「邮件发送失败，请检查 SMTP 配置」）。
- **webpage 源页面改版**：提取 0 链接不算错误；只有 HTTP 层失败才标 error。

## 11. 测试（pytest，后端为主）

- **适配器解析**：用保存的真实样本（阿里云 RSS XML、火山文档页 HTML——含 `_ROUTER_DATA`、通用网页 HTML）做 fixture，断言解析出的条目结构；火山适配器额外覆盖「更新时间变化产生新条目、未变化不产生」两种情形。
- **关键词匹配**：大小写、OR 语义、matched_keywords 记录。
- **去重与基线**：重复 url 不重复入库；首次抓取标记 baseline 且不进入待发集合。
- **通知**：mock SMTP——断言收件人集合（只含 notify_enabled 成员）、多条合并一封、发送失败后条目保持待发、成功后写 notified_at。
- **认证**：验证码有效期/一次性/60 秒限流、Cookie 鉴权、未登录写操作 401。
- 前端不写单测，手动验收（内部工具的性价比取舍）。

## 12. 配置与部署

环境变量（提供 `.env.example`，真实值不入库不入代码）：

```
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=<发件 QQ 邮箱>
SMTP_AUTH_CODE=<QQ 邮箱 SMTP 授权码>
SECRET_KEY=<随机字符串，签发登录 token>
FETCH_INTERVAL_MINUTES=30
DATABASE_URL=sqlite:///data/notice.db
```

前置条件：发件 QQ 邮箱需在 QQ 邮箱设置中开启 SMTP 服务并生成授权码。

运行方式：

- 本地开发：`uvicorn`（backend）+ `next dev`（frontend），无需 Docker；
- 部署：`docker-compose up -d`，backend 暴露 8000、frontend 暴露 3000，`./data/` 挂载卷持久化 SQLite。

## 13. 已确认的关键决策记录

| 决策 | 结论 |
|---|---|
| 监控源 | 内置阿里云 + 火山引擎；支持自定义 RSS 和网页链接源 |
| 筛选方式 | 可配置关键词规则（不用 LLM） |
| 提醒时机 | 发现新公告立即发，同轮合并一封 |
| 成员管理 | 邮箱验证码登录，登录邮箱即通知邮箱 |
| 技术栈 | FastAPI + Next.js/React + SQLite |
| 架构 | 单体服务（进程内定时任务），不拆 worker |
| 网页链接源 | 链接差异检测（无需配置选择器） |
| 部署 | 本地优先，Docker Compose 打包 |
