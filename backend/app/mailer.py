import html
import json
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from .config import settings


def send_email(recipients: list[str], subject: str, html: str) -> None:
    if not settings.smtp_user or not settings.smtp_auth_code:
        raise RuntimeError("SMTP 未配置：请设置 SMTP_USER 和 SMTP_AUTH_CODE 环境变量")
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr(("模型公告提醒", settings.smtp_user))
    msg["To"] = ", ".join(recipients)
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_auth_code)
        smtp.sendmail(settings.smtp_user, recipients, msg.as_string())


def build_notices_email(notices) -> tuple[str, str]:
    first = notices[0]
    if len(notices) == 1:
        subject = f"【模型公告提醒】{first.source.name}: {first.title}"
    else:
        subject = f"【模型公告提醒】{first.source.name}等 {len(notices)} 条新公告"
    blocks = []
    for n in notices:
        published = n.published_at.strftime("%Y-%m-%d %H:%M") if n.published_at else "未知"
        source_name = html.escape(n.source.name)
        title = html.escape(n.title)
        url = html.escape(n.url, quote=True)
        excerpt = html.escape((n.content or "")[:300])
        keywords = html.escape("、".join(json.loads(n.matched_keywords or "[]")))
        blocks.append(
            f'<div style="border:1px solid #ddd;border-radius:8px;padding:16px;margin-bottom:16px;">'
            f'<div style="color:#888;font-size:12px;">{source_name} · {published}'
            f'{" · 命中：" + keywords if keywords else ""}</div>'
            f'<h3 style="margin:8px 0;"><a href="{url}">{title}</a></h3>'
            f'<p style="color:#444;margin:0;">{excerpt}</p></div>'
        )
    html_body = (
        "<div style='font-family:sans-serif;max-width:680px;'>"
        + "".join(blocks)
        + "<p style='color:#aaa;font-size:12px;'>模型公告聚合平台自动发送</p></div>"
    )
    return subject, html_body


def send_login_code(email: str, code: str) -> None:
    send_email(
        [email],
        "【模型公告平台】登录验证码",
        f"<p>你的登录验证码是：<b style='font-size:20px'>{code}</b>，10 分钟内有效。</p>",
    )
