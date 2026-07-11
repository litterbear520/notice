"use client";

import { useCallback, useEffect, useState } from "react";
import { api, formatTime, NoticeList, SourceItem } from "@/lib/api";

const PAGE_SIZE = 20;

export default function Home() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [matchedOnly, setMatchedOnly] = useState(true);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<NoticeList | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<SourceItem[]>("/api/sources").then(setSources).catch(() => {});
  }, []);

  const load = useCallback(() => {
    const params = new URLSearchParams({
      matched_only: String(matchedOnly),
      page: String(page),
      page_size: String(PAGE_SIZE),
    });
    if (sourceId) params.set("source_id", sourceId);
    if (search) params.set("q", search);
    api<NoticeList>(`/api/notices?${params}`)
      .then((d) => { setData(d); setError(""); })
      .catch((e) => setError(e.message));
  }, [sourceId, matchedOnly, search, page]);

  useEffect(load, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div>
      <h2 className="page-title">公告时间线</h2>
      <p className="page-desc">聚合各模型厂商的官方公告，命中关键词的公告会触发邮件提醒。</p>
      <div className="toolbar">
        <select value={sourceId} onChange={(e) => { setSourceId(e.target.value); setPage(1); }}>
          <option value="">全部源</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <label className="check">
          <input
            type="checkbox"
            checked={matchedOnly}
            onChange={(e) => { setMatchedOnly(e.target.checked); setPage(1); }}
          />{" "}只看命中关键词
        </label>
        <input
          type="text"
          placeholder="搜索标题…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { setSearch(q); setPage(1); } }}
        />
        <button onClick={() => { setSearch(q); setPage(1); }}>搜索</button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {data?.items.map((n) => (
        <div className="card notice" key={n.id}>
          <div className="meta">
            <span className="tag">{n.source_name}</span>
            <span>{formatTime(n.published_at)}</span>
            {n.matched_keywords.map((k) => (
              <span className="kw" key={k}>{k}</span>
            ))}
          </div>
          <h3>
            <a href={n.url} target="_blank" rel="noreferrer">{n.title}</a>
          </h3>
        </div>
      ))}

      {data && data.items.length === 0 && <p className="empty">暂无符合条件的公告。可调整筛选，或到「源管理」手动抓取。</p>}

      <div className="pager">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
        <span>{page} / {totalPages}（共 {data?.total ?? 0} 条）</span>
        <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
      </div>
    </div>
  );
}
