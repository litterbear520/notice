"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, Me } from "@/lib/api";
import ThemeToggle from "./ThemeToggle";

const ADMIN_LINKS = [
  { href: "/sources", label: "源管理" },
  { href: "/keywords", label: "关键词" },
];

export default function NavBar() {
  const [me, setMe] = useState<Me | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    api<Me>("/api/me").then(setMe).catch(() => setMe(null));
  }, []);

  return (
    <nav className="nav">
      <Link className="brand" href="/">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="spark" src="/fable-badge.png" alt="" width={26} height={26} />
        模型公告聚合
      </Link>
      <Link className={`link${pathname === "/" ? " active" : ""}`} href="/">
        公告时间线
      </Link>
      {me?.is_admin && ADMIN_LINKS.map((l) => (
        <Link
          key={l.href}
          className={`link${pathname === l.href ? " active" : ""}`}
          href={l.href}
        >
          {l.label}
        </Link>
      ))}
      <span className="spacer" />
      <ThemeToggle />
      {me ? (
        <Link className="user" href="/settings">{me.email}</Link>
      ) : (
        <Link className="link" href="/login">登录</Link>
      )}
    </nav>
  );
}
