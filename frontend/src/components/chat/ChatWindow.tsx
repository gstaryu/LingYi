"use client";

import { useEffect, useRef, useState } from "react";
import { useChat } from "@/hooks/useChat";
import { MessageBubble } from "./MessageBubble";
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

/** 合并连续的 assistant 消息为一个气泡（diagnosis 理法 + treatment 方药 应显示为一个整体）。 */
function mergeAssistantMessages(msgs: MessageItem[]): MessageItem[] {
  const result: MessageItem[] = [];
  for (const m of msgs) {
    const last = result[result.length - 1];
    if (last && last.role === "assistant" && m.role === "assistant") {
      last.content += "\n\n" + m.content;
    } else {
      result.push({ ...m });
    }
  }
  return result;
}

export function ChatWindow({ threadId }: { threadId: string }) {
  const { messages, streaming, send, stop } = useChat(threadId);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 新消息时自动滚到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

  const lastMsg = messages[messages.length - 1];
  const showTyping = streaming && lastMsg?.role === "assistant" && lastMsg.content === "";

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
            </div>
          ) : (
            mergeAssistantMessages(messages).map((m, i) => <MessageBubble key={i} message={m} />)
          )}
          {showTyping && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-sm bg-muted px-4 py-3 text-sm text-muted-foreground">
                思考中...
              </div>
            </div>
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
