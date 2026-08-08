"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamChat } from "@/lib/stream";
import { api } from "@/lib/api";
import type { ConsultationNote, MessageItem, Stage } from "@/lib/types";
import { toast } from "sonner";

/**
 * 流式对话 Hook。
 *
 * - 切换 threadId 时加载历史消息（GET /threads/{id}/messages）。
 * - send() 调用 SSE 流式接口，逐 token 追加到助手消息。
 * - done 事件回传 thread_id（新会话首次发送时），并刷新会话列表与画像。
 * - 会诊笔记（notes）附加到对应的助手消息上（per-message），而非全局状态。
 * - stop() 通过 AbortController 中止流。
 */
export function useChat(threadId: string, initialMessages: MessageItem[] = []) {
  const [messages, setMessages] = useState<MessageItem[]>(initialMessages);
  const [streaming, setStreaming] = useState(false);
  const [stages, setStages] = useState<Stage[]>([]);
  const [showTimeline, setShowTimeline] = useState(false);
  const [currentThreadId, setCurrentThreadId] = useState(threadId);
  const abortRef = useRef<AbortController | null>(null);
  const qc = useQueryClient();

  // 切换会话时加载历史
  useEffect(() => {
    setCurrentThreadId(threadId);
    setStages([]);
    setShowTimeline(false);
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
      setStages([]);
      setShowTimeline(true);

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
                  let newContent = last.content + ev.content;
                  // Dedup: when the adversarial reviewer rejects the first
                  // prescription, synthesis re-runs and its tokens are
                  // appended to the same bubble.  Detect the second
                  // 【辨证结论】 (which only appears when a new synthesis
                  // starts after a complete first one) and truncate
                  // everything before it so only the final approved
                  // prescription is visible during streaming.
                  const bzMatches = newContent.match(/【辨证结论】/g);
                  if (bzMatches && bzMatches.length > 1) {
                    const lastBz = newContent.lastIndexOf("【辨证结论】");
                    newContent = newContent.slice(lastBz);
                  }
                  copy[copy.length - 1] = { role: "assistant", content: newContent };
                  return copy;
                });
              } else if (ev.type === "stage") {
                setStages((prev) => {
                  // 新阶段开始：将之前仍在 start 的阶段标记为 done
                  let next = prev;
                  if (ev.status === "start") {
                    next = prev.map((s) => (s.status === "start" ? { ...s, status: "done" as const } : s));
                    // 避免重复追加同一阶段
                    if (!next.some((s) => s.stage === ev.stage)) {
                      next = [...next, { stage: ev.stage, label: ev.label, status: "start" }];
                    } else {
                      next = next.map((s) => (s.stage === ev.stage ? { ...s, status: "start" as const } : s));
                    }
                  } else {
                    next = prev.map((s) => (s.stage === ev.stage ? { ...s, status: "done" as const } : s));
                  }
                  return next;
                });
              } else if (ev.type === "done") {
                const tid = ev.thread_id || currentThreadId;
                if (ev.thread_id) setCurrentThreadId(ev.thread_id);
                // 将会诊笔记附加到对应的助手消息（per-message 持久化）
                const incomingNotes: ConsultationNote[] | undefined = ev.notes;
                if (incomingNotes && incomingNotes.length > 0) {
                  setMessages((m) => {
                    const copy = [...m];
                    for (let i = copy.length - 1; i >= 0; i--) {
                      if (copy[i].role === "assistant") {
                        copy[i] = { ...copy[i], notes: incomingNotes };
                        break;
                      }
                    }
                    return copy;
                  });
                }
                // 新会话创建/画像更新后刷新列表
                qc.invalidateQueries({ queryKey: ["threads"] });
                qc.invalidateQueries({ queryKey: ["profile"] });
                // 会话命名是后台异步，延迟刷新确保新标题可见
                setTimeout(() => qc.invalidateQueries({ queryKey: ["threads"] }), 6000);
                setTimeout(() => qc.invalidateQueries({ queryKey: ["threads"] }), 12000);
                setTimeout(() => qc.invalidateQueries({ queryKey: ["profile"] }), 8000);
                // 同步后端权威状态：确保所有消息（含 inquiry 过渡语等非流式消息）按正确顺序显示
                // 同步时保留 per-message notes（通过内容匹配）
                if (tid) {
                  api
                    .getMessages(tid)
                    .then((msgs) => {
                      setMessages((prev) => {
                        // 从现有消息中收集 notes（按内容匹配）
                        const notesByContent = new Map<string, ConsultationNote[]>();
                        for (const m of prev) {
                          if (m.notes && m.notes.length > 0) {
                            notesByContent.set(m.content, m.notes);
                          }
                        }
                        if (notesByContent.size === 0) return msgs;
                        return msgs.map((m) => ({
                          ...m,
                          notes: notesByContent.get(m.content),
                        }));
                      });
                    })
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
        // Keep timeline visible 3s after streaming ends so user sees completed stages
        setTimeout(() => setShowTimeline(false), 3000);
        abortRef.current = null;
      }
    },
    [streaming, currentThreadId, qc]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  return { messages, streaming, stages, showTimeline, send, stop, currentThreadId };
}
