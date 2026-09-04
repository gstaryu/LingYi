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
 * - 会诊笔记（notes）与会诊阶段轨迹（stages）附加到对应的助手消息上（per-message），
 *   完成后以摘要条形式保留，不再整体消失。
 * - stop() 通过 AbortController 中止流。
 */

/** stage 事件归约：新阶段开始时将仍在 start 的前序阶段标记为 done，避免重复追加；
 *  done 事件可携带会诊笔记（note），随阶段条目持久化（渐进揭示）。 */
function reduceStages(
  prev: Stage[],
  ev: { stage: string; label: string; status: "start" | "done"; note?: ConsultationNote }
): Stage[] {
  if (ev.status === "start") {
    let next = prev.map((s) => (s.status === "start" ? { ...s, status: "done" as const } : s));
    if (!next.some((s) => s.stage === ev.stage)) {
      next = [...next, { stage: ev.stage, label: ev.label, status: "start" }];
    } else {
      next = next.map((s) =>
        s.stage === ev.stage ? { ...s, status: "start" as const, note: undefined } : s
      );
    }
    return next;
  }
  return prev.map((s) =>
    s.stage === ev.stage ? { ...s, status: "done" as const, note: ev.note } : s
  );
}

export function useChat(threadId: string, initialMessages: MessageItem[] = []) {
  const [messages, setMessages] = useState<MessageItem[]>(initialMessages);
  const [streaming, setStreaming] = useState(false);
  const [currentThreadId, setCurrentThreadId] = useState(threadId);
  const abortRef = useRef<AbortController | null>(null);
  /** 轮次序号：每次 send 递增。用于丢弃迟到的上一轮 resync（防止覆盖新一轮的乐观消息）。 */
  const turnSeqRef = useRef(0);
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
      const myTurn = ++turnSeqRef.current;
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
                  copy[copy.length - 1] = { ...last, content: newContent };
                  return copy;
                });
              } else if (ev.type === "stage") {
                // 阶段事件实时写入最后一条助手消息（per-message 轨迹）
                setMessages((m) => {
                  const copy = [...m];
                  for (let i = copy.length - 1; i >= 0; i--) {
                    if (copy[i].role === "assistant") {
                      copy[i] = { ...copy[i], stages: reduceStages(copy[i].stages ?? [], ev) };
                      break;
                    }
                  }
                  return copy;
                });
              } else if (ev.type === "done") {
                const tid = ev.thread_id || currentThreadId;
                if (ev.thread_id) setCurrentThreadId(ev.thread_id);
                // 将会诊笔记与用时附加到对应的助手消息（per-message 持久化）
                const incomingNotes: ConsultationNote[] | undefined = ev.notes;
                const elapsedMs = ev.elapsed_ms;
                setMessages((m) => {
                  const copy = [...m];
                  for (let i = copy.length - 1; i >= 0; i--) {
                    if (copy[i].role === "assistant") {
                      copy[i] = {
                        ...copy[i],
                        ...(incomingNotes && incomingNotes.length > 0 ? { notes: incomingNotes } : {}),
                        ...(typeof elapsedMs === "number" ? { elapsedMs } : {}),
                      };
                      break;
                    }
                  }
                  return copy;
                });
                // 新会话创建/画像更新后刷新列表
                qc.invalidateQueries({ queryKey: ["threads"] });
                qc.invalidateQueries({ queryKey: ["profile"] });
                // 会话命名是后台异步，延迟刷新确保新标题可见
                setTimeout(() => qc.invalidateQueries({ queryKey: ["threads"] }), 6000);
                setTimeout(() => qc.invalidateQueries({ queryKey: ["threads"] }), 12000);
                setTimeout(() => qc.invalidateQueries({ queryKey: ["profile"] }), 8000);
                // 同步后端权威状态：确保所有消息（含 inquiry 过渡语等非流式消息）按正确顺序显示
                // 同步时保留 per-message extras：notes / stages / elapsedMs（先按内容匹配，
                // 匹配不上时兜底挂到最后一条助手消息——流式气泡可能被截断/重写导致内容不一致）
                // 守卫：若在 getMessages 返回前用户已开启新一轮（send），此结果已过期，直接丢弃，
                // 否则会把新一轮的乐观消息（用户消息+流式气泡）整体覆盖掉。
                if (tid) {
                  const seq = turnSeqRef.current;
                  api
                    .getMessages(tid)
                    .then((msgs) => {
                      if (turnSeqRef.current !== seq) return; // 已开新轮，丢弃过期 resync
                      setMessages((prev) => {
                        const hasExtras = (m: MessageItem) =>
                          Boolean(
                            m.notes?.length || m.stages?.length || typeof m.elapsedMs === "number"
                          );
                        const extrasByContent = new Map<string, MessageItem>();
                        for (const m of prev) {
                          if (hasExtras(m)) extrasByContent.set(m.content, m);
                        }
                        const merged = msgs.map((m) => {
                          const e = extrasByContent.get(m.content);
                          if (!e) return m;
                          return {
                            ...m,
                            notes: e.notes,
                            stages: e.stages,
                            elapsedMs: e.elapsedMs,
                          };
                        });
                        // 兜底：最后一条助手消息没有 extras 时，把本轮流式消息的 extras 挂上去
                        const streamedLast = prev[prev.length - 1];
                        if (streamedLast?.role === "assistant" && hasExtras(streamedLast)) {
                          for (let i = merged.length - 1; i >= 0; i--) {
                            if (merged[i].role === "assistant") {
                              if (!hasExtras(merged[i])) {
                                merged[i] = {
                                  ...merged[i],
                                  notes: streamedLast.notes,
                                  stages: streamedLast.stages,
                                  elapsedMs: streamedLast.elapsedMs,
                                };
                              }
                              break;
                            }
                          }
                        }
                        return merged;
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
