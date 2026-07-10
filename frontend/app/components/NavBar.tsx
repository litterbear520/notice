"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Me } from "@/lib/api";

export default function NavBar() {
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/api/me").then(setMe).catch(() => setMe(null));
  }, []);

  return (
    <nav className="nav">
      <span className="brand">📢 模型公告聚合</span>
      <Link className="link" href="/">公告时间线</Link>
      <Link className="link" href="/sources">源管理</Link>
      <Link className="link" href="/keywords">关键词</Link>
      <span className="spacer" />
      {me ? (
        <Link className="user" href="/settings">{me.email}</Link>
      ) : (
        <Link className="link" href="/login">登录</Link>
      )}
    </nav>
  );
}
