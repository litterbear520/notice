export interface NoticeItem {
  id: number;
  source_id: number;
  source_name: string;
  title: string;
  url: string;
  excerpt: string;
  published_at: string;
  matched: boolean;
  matched_keywords: string[];
}

export interface NoticeList {
  total: number;
  page: number;
  page_size: number;
  items: NoticeItem[];
}

export interface SourceItem {
  id: number;
  name: string;
  type: string;
  url: string;
  enabled: boolean;
  is_builtin: boolean;
  last_fetch_at: string | null;
  last_fetch_status: string | null;
  last_error: string | null;
}

export interface KeywordItem {
  id: number;
  word: string;
  enabled: boolean;
}

export interface Me {
  email: string;
  notify_enabled: boolean;
  is_admin: boolean;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data as { detail?: string }).detail || `请求失败 (${res.status})`);
  }
  return data as T;
}

// 摘要由后端截断原文得来，可能残留 Markdown/HTML 语法，展示前清洗为纯文本
export function cleanExcerpt(raw: string | null | undefined): string {
  if (!raw) return "";
  return raw
    .replace(/<[^>]*>/g, " ")                  // 完整 HTML 标签
    .replace(/<[^>]*$/, "")                    // 截断处的残缺标签，如 <span id="
    .replace(/&[a-zA-Z#0-9]+;/g, " ")          // HTML 实体
    .replace(/!\[[^\]]*\]\s*\([^)]*\)/g, " ")  // Markdown 图片
    .replace(/\[([^\]]*)\]\s*\([^)]*\)/g, "$1") // Markdown 链接 → 保留文字
    .replace(/https?:\/\/\S+/g, " ")           // 裸 URL
    .replace(/[#*`>|]+/g, " ")                 // Markdown 标记符
    .replace(/[（(]\s*[)）]/g, " ")            // 清洗后残留的空括号
    .replace(/\s+/g, " ")
    .trim();
}

export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleString("zh-CN", {
    hour12: false,
  });
}
