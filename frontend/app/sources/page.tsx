"use client";

import { useCallback, useEffect, useState } from "react";
import { api, formatTime, SourceItem } from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  aliyun_rss: "内置·阿里云RSS",
  volcengine: "内置·火山引擎",
  rss: "RSS",
  webpage: "网页链接",
};

export default function SourcesPage() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [type, setType] = useState("rss");
  const [url, setUrl] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editUrl, setEditUrl] = useState("");

  const load = useCallback(() => {
    api<SourceItem[]>("/api/sources").then(setSources).catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    try {
      setError("");
      await fn();
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const add = () =>
    run(async () => {
      await api("/api/sources", {
        method: "POST",
        body: JSON.stringify({ name, type, url }),
      });
      setName(""); setUrl("");
    });

  const toggle = (s: SourceItem) =>
    run(() => api(`/api/sources/${s.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !s.enabled }),
    }));

  const remove = (s: SourceItem) => {
    if (!confirm(`确认删除源「${s.name}」？其下所有公告也会被删除。`)) return;
    run(() => api(`/api/sources/${s.id}`, { method: "DELETE" }));
  };

  const fetchNow = async (s: SourceItem) => {
    setBusy(s.id);
    await run(async () => {
      const r = await api<{ new_items: number }>(`/api/sources/${s.id}/fetch`, { method: "POST" });
      alert(`「${s.name}」抓取完成，新增 ${r.new_items} 条`);
    });
    setBusy(null);
  };

  const startEdit = (s: SourceItem) => {
    setEditingId(s.id);
    setEditName(s.name);
    setEditUrl(s.url);
  };

  const cancelEdit = () => setEditingId(null);

  const saveEdit = (s: SourceItem) =>
    run(async () => {
      const body: { name: string; url?: string } = { name: editName };
      if (!s.is_builtin) body.url = editUrl;
      await api(`/api/sources/${s.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setEditingId(null);
    });

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>源管理</h2>
      {error && <div className="error-box">{error}（管理操作需要先登录）</div>}

      <div className="card">
        <div className="form-row">
          <input type="text" placeholder="源名称" value={name} onChange={(e) => setName(e.target.value)} />
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="rss">RSS 订阅</option>
            <option value="webpage">网页链接</option>
          </select>
          <input type="text" placeholder="https://…" style={{ flex: 1, minWidth: 240 }}
                 value={url} onChange={(e) => setUrl(e.target.value)} />
          <button className="primary" onClick={add} disabled={!name || !url}>添加源</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>名称</th><th>类型</th><th>最近抓取</th><th>状态</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id} style={{ opacity: s.enabled ? 1 : 0.5 }}>
              {editingId === s.id ? (
                <td>
                  <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} />
                  {s.is_builtin ? (
                    <div style={{ fontSize: 12, color: "#9ca3af", wordBreak: "break-all" }}>{s.url}</div>
                  ) : (
                    <input type="text" style={{ marginTop: 4 }}
                           value={editUrl} onChange={(e) => setEditUrl(e.target.value)} />
                  )}
                </td>
              ) : (
                <td>
                  {s.name}
                  <div style={{ fontSize: 12, color: "#9ca3af", wordBreak: "break-all" }}>{s.url}</div>
                </td>
              )}
              <td>{TYPE_LABELS[s.type] ?? s.type}</td>
              <td>{formatTime(s.last_fetch_at)}</td>
              <td>
                {s.last_fetch_status === "ok" && <span className="status-ok">正常</span>}
                {s.last_fetch_status === "error" && (
                  <span className="status-error" title={s.last_error ?? ""}>
                    失败：{(s.last_error ?? "").slice(0, 80)}
                  </span>
                )}
                {!s.last_fetch_status && <span style={{ color: "#9ca3af" }}>未抓取</span>}
              </td>
              <td>
                <div className="form-row">
                  {editingId === s.id ? (
                    <>
                      <button className="primary" onClick={() => saveEdit(s)} disabled={!editName}>保存</button>
                      <button onClick={cancelEdit}>取消</button>
                    </>
                  ) : (
                    <>
                      <button onClick={() => fetchNow(s)} disabled={busy === s.id}>
                        {busy === s.id ? "抓取中…" : "立即抓取"}
                      </button>
                      <button onClick={() => toggle(s)}>{s.enabled ? "停用" : "启用"}</button>
                      <button onClick={() => startEdit(s)}>编辑</button>
                      {!s.is_builtin && (
                        <button className="danger" onClick={() => remove(s)}>删除</button>
                      )}
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
