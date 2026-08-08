"use client";

import { useEffect, useRef, useState } from "react";
import { useChat } from "@/hooks/useChat";
import { MessageBubble } from "./MessageBubble";
import { ConsultationTimeline } from "./ConsultationTimeline";
import { ConsultationNotes } from "./ConsultationNotes";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import type { MessageItem } from "@/lib/types";
import { toast } from "sonner";
import { Send, Square, Paperclip, Leaf, X } from "lucide-react";

interface UploadedFile {
  path: string;
  filename: string;
}

/** 合并连续的 assistant 消息为一个气泡（diagnosis 理法 + treatment 方药 应显示为一个整体）。
 *  安全网去重：若连续两条 assistant 消息都含【处方建议】（synthesis 重试残留），
 *  仅保留最后一条（最终批准的处方），避免重复渲染辨证/处方块。 */
export function mergeAssistantMessages(msgs: MessageItem[]): MessageItem[] {
  const result: MessageItem[] = [];
  for (const m of msgs) {
    const last = result[result.length - 1];
    if (last && last.role === "assistant" && m.role === "assistant") {
      const lastHasRx = last.content.includes("【处方建议】");
      const mHasRx = m.content.includes("【处方建议】");
      if (lastHasRx && mHasRx) {
        // Both are synthesis outputs (retry) — replace with the latest
        result[result.length - 1] = { ...m };
      } else {
        last.content += "\n\n" + m.content;
      }
    } else {
      result.push({ ...m });
    }
  }
  return result;
}

export function ChatWindow({ threadId }: { threadId: string }) {
  const { messages, streaming, stages, showTimeline, send, stop } = useChat(threadId);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 新消息时自动滚到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, stages]);

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const res = await api.upload(file);
      setFiles((f) => [...f, res]);
      toast.success(`已上传：${res.filename}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  function handleSend() {
    if (!input.trim() || streaming) return;
    send(input, files.map((f) => f.path));
    setInput("");
    setFiles([]);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const merged = mergeAssistantMessages(messages);
  const lastMsg = merged[merged.length - 1];
  const showTimelineForLast = showTimeline && lastMsg?.role === "assistant";
  const examplePrompts = ["肚子胀、怕冷、大便稀", "最近总是失眠多梦", "头痛、眼睛干涩"];

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                <Leaf className="h-8 w-8 text-primary" aria-hidden />
              </div>
              <h2 className="text-xl font-semibold">灵医问诊</h2>
              <p className="mt-2 max-w-md text-muted-foreground">
                请描述您的症状，我将按中医"理法方药"为您分析。可上传病历文件辅助诊断。
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {examplePrompts.map((p) => (
                  <button
                    key={p}
                    onClick={() => setInput(p)}
                    className="rounded-full border border-border/60 bg-background/60 px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            merged.map((m, i) => {
              const isLast = i === merged.length - 1;
              const isStreamingLast = streaming && isLast && m.role === "assistant";
              const showTimelineHere = (isStreamingLast || (showTimelineForLast && isLast)) && stages.length > 0;
              return (
                <div key={i} className="space-y-2">
                  {showTimelineHere && (
                    <ConsultationTimeline stages={stages} streaming={streaming} />
                  )}
                  <MessageBubble message={m} isStreaming={isStreamingLast} />
                  {!streaming && m.role === "assistant" && m.notes && m.notes.length > 0 && (
                    <ConsultationNotes notes={m.notes} />
                  )}
                </div>
              );
            })
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t bg-background px-4 py-3">
        <div className="mx-auto max-w-3xl">
          {files.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {files.map((f) => (
                <span
                  key={f.path}
                  className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-xs"
                >
                  <Paperclip className="h-3 w-3" aria-hidden />
                  {f.filename}
                  <button
                    onClick={() => setFiles((arr) => arr.filter((x) => x.path !== f.path))}
                    className="ml-1 hover:text-destructive"
                    aria-label={`移除 ${f.filename}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
                e.target.value = "";
              }}
            />
            <Button
              variant="outline"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || streaming}
              aria-label="上传病历文件"
              title="上传病历文件（PDF/DOCX/TXT）"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="请描述您的症状..."
              rows={1}
              className="min-h-[44px] max-h-40 resize-none"
              disabled={streaming}
            />
            {streaming ? (
              <Button variant="destructive" size="icon" onClick={stop} aria-label="停止生成">
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button size="icon" onClick={handleSend} disabled={!input.trim()} aria-label="发送">
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
          <p className="mt-1.5 text-center text-xs text-muted-foreground">
            ⚠️ 内容仅供参考，不能替代执业中医师面诊，请勿自行抓药。
          </p>
        </div>
      </div>
    </div>
  );
}
