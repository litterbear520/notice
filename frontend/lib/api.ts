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

export function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleString("zh-CN", {
    hour12: false,
  });
}
