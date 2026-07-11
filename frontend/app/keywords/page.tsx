"use client";

import { useCallback, useEffect, useState } from "react";
import { api, KeywordItem } from "@/lib/api";

export default function KeywordsPage() {
  const [keywords, setKeywords] = useState<KeywordItem[]>([]);
  const [word, setWord] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<KeywordItem[]>("/api/keywords").then(setKeywords).catch((e) => setError(e.message));
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
      await api("/api/keywords", { method: "POST", body: JSON.stringify({ word }) });
      setWord("");
    });

  return (
    <div>
      <h2 className="page-title">关键词管理</h2>
      <p className="page-desc">
        公告标题或正文命中任一启用的关键词（不区分大小写）即触发邮件提醒。
      </p>
      {error && <div className="error-box">{error}（管理操作需要先登录）</div>}

      <div className="card">
        <div className="form-row">
          <input type="text" placeholder="新关键词，如：下线" value={word}
                 onChange={(e) => setWord(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && word) add(); }} />
          <button className="primary" onClick={add} disabled={!word}>添加</button>
        </div>
      </div>

      <div className="table-wrap">
      <table>
        <thead>
          <tr><th>关键词</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          {keywords.map((k) => (
            <tr key={k.id} style={{ opacity: k.enabled ? 1 : 0.5 }}>
              <td>{k.word}</td>
              <td>{k.enabled ? <span className="status-ok">启用</span> : "停用"}</td>
              <td>
                <div className="form-row">
                  <button onClick={() => run(() => api(`/api/keywords/${k.id}`, {
                    method: "PATCH", body: JSON.stringify({ enabled: !k.enabled }),
                  }))}>{k.enabled ? "停用" : "启用"}</button>
                  <button className="danger" onClick={() => run(() =>
                    api(`/api/keywords/${k.id}`, { method: "DELETE" })
                  )}>删除</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
