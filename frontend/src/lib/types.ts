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
  notes?: ConsultationNote[];
  /** 会诊阶段轨迹（per-message 持久，流式中实时更新，完成后保留为摘要条） */
  stages?: Stage[];
  /** 单轮响应用时（毫秒，来自 done 事件） */
  elapsedMs?: number;
}

export interface UserProfile {
  patient_id: string;
  constitution: string;
  allergies: string;
  past_history: string[];
}

export interface ProfileUpdate {
  constitution?: string;
  allergies?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UploadResponse {
  path: string;
  filename: string;
}

/** 会诊笔记条目（多智能体专家输出，对应后端 consultation_notes）。 */
export interface ConsultationNote {
  specialist: string;
  syndrome?: string;
  recommended_formulas?: string[];
  herb_notes?: unknown[];
  safety_warnings?: string[];
  reasoning?: string;
  confidence?: number;
  modifications?: string;
  approved?: boolean;
  issues?: string[];
  suggestions?: string;
  [k: string]: unknown;
}

/** 会诊阶段（用于时间线展示）。note=该阶段完成时的会诊笔记（渐进揭示）。 */
export interface Stage {
  stage: string;
  label: string;
  status: "start" | "done";
  note?: ConsultationNote;
}

/** SSE 流式事件（POST /api/chat?stream=true） */
export type ChatStreamEvent =
  | { type: "token"; content: string }
  | {
      type: "stage";
      stage: string;
      label: string;
      status: "start" | "done";
      note?: ConsultationNote;
    }
  | {
      type: "done";
      thread_id: string;
      notes?: ConsultationNote[];
      diagnosis?: string;
      elapsed_ms?: number;
    }
  | { type: "error"; message: string };
