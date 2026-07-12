import { useAuthStore } from "@/stores/auth";
import type {
  ChatRequest,
  ChatResponse,
  MessageItem,
  ThreadInfo,
  TokenResponse,
  UploadResponse,
  UserProfile,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "") + "/api";

/** 带 HTTP 状态码的错误，便于上层按状态区分处理。 */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** 从 auth store 取 Bearer 头（非交互场景用 getState，避免 hook 限制）。 */
function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** 401 时清登录态并跳登录页。 */
function handleUnauthorized() {
  useAuthStore.getState().logout();
  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...options.headers,
    },
  });

  if (res.status === 401) {
    handleUnauthorized();
    throw new ApiError(401, "未登录或登录已过期");
  }
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`;
    try {
      const d = await res.json();
      msg = d.detail || msg;
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export const api = {
  // 认证
  login: (username: string, password: string) =>
    request<TokenResponse>("/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  register: (username: string, password: string) =>
    request<{ status: string; message: string }>("/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  // 会话
  listThreads: () => request<ThreadInfo[]>("/threads"),
  createThread: (title: string) =>
    request<ThreadInfo>("/threads", { method: "POST", body: JSON.stringify({ title }) }),
  renameThread: (id: string, title: string) =>
    request(`/threads/${id}`, { method: "PUT", body: JSON.stringify({ new_title: title }) }),
  deleteThread: (id: string) => request(`/threads/${id}`, { method: "DELETE" }),
  getMessages: (id: string) => request<MessageItem[]>(`/threads/${id}/messages`),

  // 画像
  getProfile: (username: string) => request<UserProfile>(`/profiles/${username}`),

  // 对话（非流式，流式见 lib/stream.ts）
  chat: (req: ChatRequest) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(req) }),

  // 文件上传（multipart，不带 Content-Type 让浏览器自动设置 boundary）
  upload: async (file: File): Promise<UploadResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${API_BASE}/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError(401, "未登录");
    }
    if (!res.ok) {
      let msg = "上传失败";
      try {
        const d = await res.json();
        msg = d.detail || msg;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, msg);
    }
    return res.json();
  },
};
