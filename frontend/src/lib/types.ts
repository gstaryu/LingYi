/**
 * 后端 API 类型定义（对应 lingyi/api/schemas.py）。
 * 前端所有请求/响应均用这些类型，保证与后端契约一致。
 */

export interface ChatRequest {
  message: string;
  thread_id?: string;
  files?: string[];
}

export interface ChatResponse {
  response: string;
  thread_id: string;
  intent_type: "chat" | "consult" | "diagnose" | "safety_rejected" | string;
  symptoms: string[];
}

export interface ThreadInfo {
  thread_id: string;
  title: string;
  created_at: string;
}

export interface MessageItem {
  role: "user" | "assistant";
  content: string;
}

export interface UserProfile {
  patient_id: string;
  constitution: string;
  allergies: string;
  past_history: string[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UploadResponse {
  path: string;
  filename: string;
}

/** SSE 流式事件（POST /api/chat?stream=true） */
export type ChatStreamEvent =
  | { type: "token"; content: string }
  | { type: "done"; thread_id: string }
  | { type: "error"; message: string };
