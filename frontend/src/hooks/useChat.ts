"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamChat } from "@/lib/stream";
import { api } from "@/lib/api";
import type { MessageItem } from "@/lib/types";
import { toast } from "sonner";

/**
 * 流式对话 Hook。
 *
 * - 切换 threadId 时加载历史消息（GET /threads/{id}/messages）。
 * - send() 调用 SSE 流式接口，逐 token 追加到助手消息。
 * - done 事件回传 thread_id（新会话首次发送时），并刷新会话列表与画像。
 * - stop() 通过 AbortController 中止流。
 */
export function useChat(threadId: string, initialMessages: MessageItem[] = []) {
  const [messages, setMessages] = useState<MessageItem[]>(initialMessages);
  const [streaming, setStreaming] = useState(false);
  const [currentThreadId, setCurrentThreadId] = useState(threadId);
  const abortRef = useRef<AbortController | null>(null);
  const qc = useQueryClient();

  // 切换会话时加载历史
  useEffect(() => {
    setCurrentThreadId(threadId);
    if (!threadId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    api
      .getMessages(threadId)
      .then((msgs) => !cancelled && setMessages(msgs))
      .catch(() => !cancelled && setMessages([]));
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  const send = useCallback(
    async (text: string, files: string[] = []) => {
      if (!text.trim() || streaming) return;
      const userMsg: MessageItem = { role: "user", content: text };
      setMessages((m) => [...m, userMsg, { role: "assistant", content: "" }]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamChat(
          { message: text, thread_id: currentThreadId || undefined, files },
          {
            signal: controller.signal,
            onEvent: (ev) => {
              if (ev.type === "token") {
                setMessages((m) => {
                  const copy = [...m];
                  const last = copy[copy.length - 1];
                  copy[copy.length - 1] = { role: "assistant", content: last.content + ev.content };
                  return copy;
                });
              } else if (ev.type === "done") {
                const tid = ev.thread_id || currentThreadId;
                if (ev.thread_id) setCurrentThreadId(ev.thread_id);
                // 新会话创建/画像更新后刷新列表
                qc.invalidateQueries({ queryKey: ["threads"] });
                qc.invalidateQueries({ queryKey: ["profile"] });
                // 画像由 ProfileWriter 后台异步写入，done 时可能未完成，延迟再刷新一次确保更新可见
                setTimeout(() => qc.invalidateQueries({ queryKey: ["profile"] }), 8000);
                // 同步后端权威状态：确保所有消息（含 inquiry 过渡语等非流式消息）按正确顺序显示
                if (tid) {
                  api
                    .getMessages(tid)
                    .then((msgs) => setMessages(msgs))
                    .catch(() => {});
                }
              } else if (ev.type === "error") {
                toast.error(ev.message);
              }
            },
            onError: (err) => toast.error(err.message),
          }
        );
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [streaming, currentThreadId, qc]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  return { messages, streaming, send, stop, currentThreadId };
}
