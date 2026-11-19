import { useEffect, useRef, useState } from 'react';

export const community = 'cityu-hackathon';
export const topicsPath = '/api/communities/' + community + '/topics';

export interface Guest {
  guest_id: string;
  nickname: string;
}

interface Post {
  id: number;
  nickname: string;
  created_at: string;
}

export interface Topic extends Post {
  community_slug?: string;
  title: string;
  summary: string;
  comment_count: number;
}

export interface Comment extends Post {
  content: string;
}

export interface TopicDetail extends Post {
  title: string;
  content: string;
  comments: Comment[];
  hot_topic?: HotTopicSource;
}

export interface HotTopicSource {
  source: string;
  original_url: string;
}

export interface HotTopic extends HotTopicSource {
  topic_id: number;
  title: string;
  comment_count: number;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { cache: 'no-store', ...options });
  } catch (error) {
    if (options?.signal?.aborted) throw error;
    throw new Error('无法连接到服务，请检查网络后重试。');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = typeof body?.detail === 'string' ? body.detail : null;
    throw new ApiError(response.status, message ?? (
      response.status === 422 ? '请检查输入的内容和长度。' : '服务暂时不可用，请稍后重试。'
    ));
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function post<T>(path: string, body: object) {
  return api<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function usePolling<T>(path: string | null, interval = 2000) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const refresh = useRef<() => void>(() => {});

  useEffect(() => {
    if (!path) return;
    const endpoint = path;
    let active: AbortController | undefined;
    let stopped = false;
    async function load(force = false) {
      if (document.hidden && !force) return;
      if (active && !force) return;
      active?.abort();
      const request = new AbortController();
      active = request;
      const timeout = window.setTimeout(() => request.abort(), 8000);
      try {
        const result = await api<T>(endpoint, { signal: request.signal });
        if (stopped || active !== request) return;
        setData(result);
        setError(undefined);
      } catch (reason) {
        if (stopped || active !== request) return;
        setError(request.signal.aborted
          ? new Error('连接超时，正在重试。')
          : reason instanceof Error ? reason : new Error('刷新失败。'));
      } finally {
        window.clearTimeout(timeout);
        if (active === request) active = undefined;
      }
    }

    refresh.current = () => void load(true);
    void load();
    const timer = window.setInterval(() => void load(), interval);
    const visible = () => void load();
    document.addEventListener('visibilitychange', visible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
      active?.abort();
    };
  }, [path, interval]);

  return { data, error, refresh: () => refresh.current() };
}
