import { useAuthStore } from "@/stores/auth";
import type { ChatRequest, ChatStreamEvent } from "./types";

/**
 * SSE 流式对话：POST /api/chat?stream=true
 *
 * 后端返回 text/event-stream，每行 `data: {json}\n\n`，事件为：
 *   {token: "..."} | {done: true, thread_id: "..."} | {error: "..."}
 *
 * 用 fetch + ReadableStream 解析 SSE，逐事件回调，支持 AbortController 中止。
 */

export interface StreamOptions {
  onEvent: (event: ChatStreamEvent) => void;
  onError?: (err: Error) => void;
  signal?: AbortSignal;
}

export async function streamChat(req: ChatRequest, opts: StreamOptions): Promise<void> {
  const token = useAuthStore.getState().token;
  const url = (process.env.NEXT_PUBLIC_API_URL || "") + "/api/chat?stream=true";
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(req),
    signal: opts.signal,
  });

  if (res.status === 401) {
    useAuthStore.getState().logout();
    if (typeof window !== "undefined") window.location.href = "/login";
    opts.onError?.(new Error("未登录或登录已过期"));
    return;
  }
  if (!res.ok || !res.body) {
    let msg = `请求失败 (${res.status})`;
    try {
      const d = await res.json();
      msg = d.detail || msg;
    } catch {
      /* ignore */
    }
    opts.onError?.(new Error(msg));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE 以双换行分隔事件
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const dataLine = raw
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trim())
          .join("");
        if (!dataLine) continue;
        try {
          const parsed = JSON.parse(dataLine);
          if (parsed.token) {
            opts.onEvent({ type: "token", content: parsed.token });
          } else if (parsed.done) {
            opts.onEvent({ type: "done", thread_id: parsed.thread_id ?? "" });
          } else if (parsed.error) {
            opts.onEvent({ type: "error", message: parsed.error });
          }
        } catch {
          /* 跳过无法解析的块 */
        }
      }
    }
  } catch (err) {
    // AbortError 属正常中止，不报错
    if ((err as Error).name !== "AbortError") {
      opts.onError?.(err as Error);
    }
  }
}
