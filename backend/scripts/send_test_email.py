"""手动测试邮件推送：关闭代理（TUN/系统代理）后运行。

用法（在 backend 目录下）:
    ./.venv/bin/python scripts/send_test_email.py [收件邮箱]

不传收件邮箱时默认发到 1194997349@qq.com。
"""
import socket
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app import mailer
from app.config import settings
from app.db import SessionLocal
from app.models import Notice

recipient = sys.argv[1] if len(sys.argv) > 1 else "1194997349@qq.com"

# 1/2 网络预检：代理开着时 SMTP 的 TLS 握手会被出口节点掐断
print(f"1/2 检查到 {settings.smtp_host}:{settings.smtp_port} 的连通性 ...")
try:
    ctx = ssl.create_default_context()
    with socket.create_connection((settings.smtp_host, settings.smtp_port), timeout=10) as s:
        with ctx.wrap_socket(s, server_hostname=settings.smtp_host) as t:
            print(f"    网络正常（{t.version()}）")
except Exception as e:
    print(f"    连不上 SMTP：{type(e).__name__}: {e}")
    print("    如果代理/TUN 还开着，先关闭再重试。")
    sys.exit(1)

# 2/2 走真实代码路径：取库里最近 3 条命中关键词的公告构建邮件
with SessionLocal() as db:
    notices = list(db.scalars(
        select(Notice).where(Notice.matched == True)  # noqa: E712
        .order_by(Notice.published_at.desc()).limit(3)
    ))

if notices:
    subject, html_body = mailer.build_notices_email(notices)
else:
    subject = "【模型公告提醒】推送测试"
    html_body = "<p>这是一封测试邮件，收到即说明 SMTP 推送链路正常。</p>"

print(f"2/2 发送「{subject}」到 {recipient} ...")
mailer.send_email([recipient], subject, html_body)
print("    发送成功，去邮箱查收（注意可能进垃圾箱）。")
