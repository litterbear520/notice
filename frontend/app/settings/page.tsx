"use client";

import { useEffect, useState } from "react";
import { api, formatTime, Me } from "@/lib/api";

interface Member {
  email: string;
  notify_enabled: boolean;
  last_login_at: string | null;
}

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Me>("/api/me")
      .then((m) => {
        setMe(m);
        if (m.is_admin) return api<Member[]>("/api/users").then(setMembers);
      })
      .catch(() => { window.location.href = "/login"; });
  }, []);

  const toggleNotify = async () => {
    if (!me) return;
    try {
      const updated = await api<Me>("/api/me", {
        method: "PATCH",
        body: JSON.stringify({ notify_enabled: !me.notify_enabled }),
      });
      setMe(updated);
      setMembers((ms) => ms.map((m) =>
        m.email === updated.email ? { ...m, notify_enabled: updated.notify_enabled } : m
      ));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" });
    window.location.href = "/";
  };

  if (!me) return <p>加载中…</p>;

  return (
    <div>
      <h2 className="page-title">个人设置</h2>
      <p className="page-desc">管理你的邮件提醒偏好，并查看订阅成员。</p>
      {error && <div className="error-box">{error}</div>}

      <div className="card">
        <div className="form-row" style={{ justifyContent: "space-between" }}>
          <div>
            <div style={{ fontWeight: 600 }}>{me.email}</div>
            <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
              邮件提醒：{me.notify_enabled ? "已开启" : "已关闭"}
            </div>
          </div>
          <div className="form-row">
            <button onClick={toggleNotify}>
              {me.notify_enabled ? "关闭提醒" : "开启提醒"}
            </button>
            <button className="danger" onClick={logout}>退出登录</button>
          </div>
        </div>
      </div>

      {me.is_admin && (<>
      <h3 className="section-title">成员列表</h3>
      <div className="table-wrap">
      <table>
        <thead>
          <tr><th>邮箱</th><th>提醒</th><th>最近登录</th></tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.email}>
              <td>{m.email}</td>
              <td>{m.notify_enabled ? <span className="status-ok">开启</span> : "关闭"}</td>
              <td className="nowrap">{formatTime(m.last_login_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      </>)}
    </div>
  );
}
