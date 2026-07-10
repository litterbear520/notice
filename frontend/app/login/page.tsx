"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"email" | "code">("email");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const requestCode = async () => {
    try {
      setError("");
      await api("/api/auth/request-code", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setStage("code");
      setMessage(`验证码已发送到 ${email}，10 分钟内有效。`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const verify = async () => {
    try {
      setError("");
      await api("/api/auth/verify", {
        method: "POST",
        body: JSON.stringify({ email, code }),
      });
      window.location.href = "/";  // 整页刷新，让 NavBar 重新拉 /api/me
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="card" style={{ maxWidth: 420, margin: "48px auto", padding: 32 }}>
      <h2 style={{ marginBottom: 8 }}>邮箱登录</h2>
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 20 }}>
        登录即订阅：新公告提醒会发送到这个邮箱。
      </p>
      {error && <div className="error-box">{error}</div>}
      {message && <p style={{ fontSize: 13, color: "#16a34a", marginBottom: 12 }}>{message}</p>}

      {stage === "email" ? (
        <div className="form-row">
          <input type="email" placeholder="you@qq.com" style={{ flex: 1 }} value={email}
                 onChange={(e) => setEmail(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && email) requestCode(); }} />
          <button className="primary" onClick={requestCode} disabled={!email}>发送验证码</button>
        </div>
      ) : (
        <div className="form-row">
          <input type="text" placeholder="6 位验证码" style={{ flex: 1 }} value={code}
                 maxLength={6}
                 onChange={(e) => setCode(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && code.length === 6) verify(); }} />
          <button className="primary" onClick={verify} disabled={code.length !== 6}>登录</button>
          <button onClick={() => { setStage("email"); setMessage(""); }}>返回</button>
        </div>
      )}
    </div>
  );
}
