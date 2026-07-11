"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Butterfly } from "../components/Fable";

const COOLDOWN_SECONDS = 60;
const EMAIL_RE = /^\S+@\S+\.\S+$/;

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [sentEmail, setSentEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"email" | "code">("email");
  const [cooldown, setCooldown] = useState(0);
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");
  const codeRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  useEffect(() => {
    if (stage === "code") codeRef.current?.focus();
  }, [stage]);

  // 换了新邮箱不受上一个邮箱的倒计时限制（后端按邮箱限流）
  const onCooldown = cooldown > 0 && email === sentEmail;
  const emailValid = EMAIL_RE.test(email);

  const requestCode = async () => {
    if (!emailValid || sending || onCooldown) return;
    try {
      setError("");
      setSending(true);
      await api("/api/auth/request-code", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setSentEmail(email);
      setCooldown(COOLDOWN_SECONDS);
      setCode("");
      setStage("code");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const verify = async () => {
    if (code.length !== 6 || verifying) return;
    try {
      setError("");
      setVerifying(true);
      await api("/api/auth/verify", {
        method: "POST",
        body: JSON.stringify({ email: sentEmail, code }),
      });
      window.location.href = "/";  // 整页刷新，让 NavBar 重新拉 /api/me
    } catch (e) {
      setError((e as Error).message);
      setVerifying(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-logo" aria-hidden="true">
          <Butterfly size={30} tone="coral" />
        </div>

        {stage === "email" ? (
          <>
            <h2 className="login-title">登录模型公告聚合</h2>
            <p className="login-desc">输入邮箱获取验证码，登录即订阅新公告提醒。</p>
            {error && <div className="error-box">{error}</div>}
            <div className="field">
              <label htmlFor="login-email">邮箱地址</label>
              <input
                id="login-email"
                type="email"
                placeholder="you@example.com"
                value={email}
                autoFocus
                autoComplete="email"
                onChange={(e) => setEmail(e.target.value.trim())}
                onKeyDown={(e) => { if (e.key === "Enter") requestCode(); }}
              />
            </div>
            <button
              className="primary btn-block"
              onClick={requestCode}
              disabled={!emailValid || sending || onCooldown}
            >
              {sending ? "发送中…" : onCooldown ? `${cooldown} 秒后可重新发送` : "发送验证码"}
            </button>
            {onCooldown && (
              <p className="login-hint">
                验证码已发送，<button className="link-btn" onClick={() => setStage("code")}>去输入验证码</button>
              </p>
            )}
          </>
        ) : (
          <>
            <h2 className="login-title">输入验证码</h2>
            <p className="login-desc">
              已发送 6 位验证码至 <strong>{sentEmail}</strong>，10 分钟内有效。
            </p>
            {error && <div className="error-box">{error}</div>}
            <div className="field">
              <input
                ref={codeRef}
                className="code-input"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="······"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                onKeyDown={(e) => { if (e.key === "Enter") verify(); }}
              />
            </div>
            <button
              className="primary btn-block"
              onClick={verify}
              disabled={code.length !== 6 || verifying}
            >
              {verifying ? "登录中…" : "登录"}
            </button>
            <p className="login-hint">
              没有收到？
              {cooldown > 0 ? (
                <span className="muted">{cooldown} 秒后可重新发送</span>
              ) : (
                <button className="link-btn" onClick={() => { setEmail(sentEmail); requestCode(); }} disabled={sending}>
                  {sending ? "发送中…" : "重新发送"}
                </button>
              )}
              <span className="dot-sep">·</span>
              <button className="link-btn" onClick={() => { setStage("email"); setError(""); }}>
                更换邮箱
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
