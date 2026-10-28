"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useChat } from "@/hooks/useChat";
import { MessageBubble } from "./MessageBubble";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { NO_MEMBER_ID, useMemberStore } from "@/stores/member";
import { api, ApiError } from "@/lib/api";
import type { MessageItem } from "@/lib/types";
import { toast } from "sonner";
import {
  Send,
  Square,
  Paperclip,
  Leaf,
  X,
  UserRound,
  ChevronDown,
  Check,
  UserPlus,
  UserX,
} from "lucide-react";

interface UploadedFile {
  path: string;
  filename: string;
}

/** 合并连续的 assistant 消息为一个气泡（diagnosis 理法 + treatment 方药 应显示为一个整体）。
 *  安全网去重：若连续两条 assistant 消息都含【处方建议】（synthesis 重试残留），
 *  仅保留最后一条（最终批准的处方），避免重复渲染辨证/处方块。
 *  合并时保留 per-message extras（notes/stages/elapsedMs）：后者缺失时继承前者的。 */
export function mergeAssistantMessages(msgs: MessageItem[]): MessageItem[] {
  const result: MessageItem[] = [];
  for (const m of msgs) {
    const last = result[result.length - 1];
    if (last && last.role === "assistant" && m.role === "assistant") {
      const lastHasRx = last.content.includes("【处方建议】");
      const mHasRx = m.content.includes("【处方建议】");
      if (lastHasRx && mHasRx) {
        // Both are synthesis outputs (retry) — replace with the latest
        result[result.length - 1] = {
          ...m,
          notes: m.notes ?? last.notes,
          stages: m.stages ?? last.stages,
          elapsedMs: m.elapsedMs ?? last.elapsedMs,
        };
      } else {
        result[result.length - 1] = {
          ...last,
          content: last.content + "\n\n" + m.content,
          notes: last.notes ?? m.notes,
          stages: last.stages ?? m.stages,
          elapsedMs: last.elapsedMs ?? m.elapsedMs,
        };
      }
    } else {
      result.push({ ...m });
    }
  }
  return result;
}

export function ChatWindow({ threadId }: { threadId: string }) {
  const { messages, streaming, send, stop, currentThreadId } = useChat(threadId);
  const [input, setInput] = useState("");
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ==================== 咨询人 ====================
  const { activeMemberId, setActiveMember } = useMemberStore();
  const qc = useQueryClient();
  const router = useRouter();
  const { data: members } = useQuery({ queryKey: ["members"], queryFn: api.listMembers });
  const { data: threads } = useQuery({ queryKey: ["threads"], queryFn: api.listThreads });
  const [addingMember, setAddingMember] = useState(false);
  const [newMemberName, setNewMemberName] = useState("");

  // 成员列表就绪后：显式 none → null；具体 id 失效（换账号/被删）→ 回退主成员
  const memberReady = Array.isArray(members) && members.length > 0;
  const primaryMember = members?.find((m) => m.is_primary) ?? members?.[0];
  const selectedMember = memberReady
    ? activeMemberId === NO_MEMBER_ID
      ? null
      : (members!.find((m) => m.member_id === activeMemberId) ?? primaryMember)
    : undefined;
  /** 发给后端的 member_id：undefined=主成员（本人），""=不结合咨询人 */
  const sendMemberId = memberReady ? (selectedMember ? selectedMember.member_id : "") : undefined;
  const memberLabel = memberReady
    ? (selectedMember?.display_name ?? "不结合咨询人")
    : "本人";

  const createMemberMut = useMutation({
    mutationFn: (name: string) => api.createMember(name),
    onSuccess: (m) => {
      qc.invalidateQueries({ queryKey: ["members"] });
      setAddingMember(false);
      setNewMemberName("");
      toast.success(`已新增咨询人：${m.display_name}`);
      handleSelectMember(m.member_id);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "新增失败"),
  });

  const newThreadMut = useMutation({
    mutationFn: ({ title, memberId }: { title: string; memberId: string }) =>
      api.createThread(title, memberId),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      router.push(`/chat/${t.thread_id}`);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "创建会话失败"),
  });

  // 打开会话时恢复其绑定的咨询人（会话与咨询人 1:1）
  useEffect(() => {
    if (!threadId || !threads) return;
    const bound = threads.find((t) => t.thread_id === threadId)?.member_id;
    if (bound === undefined) return;
    setActiveMember(bound === "" ? NO_MEMBER_ID : bound);
  }, [threadId, threads, setActiveMember]);

  /**
   * 切换咨询人。
   *
   * 会话与咨询人 1:1 绑定：当前会话已有消息时切换，会为该咨询人新开一个会话，
   * 避免上一轮的症状进入新咨询人的上下文，或被提取进新咨询人的画像。
   */
  function handleSelectMember(id: string) {
    const currentId = selectedMember ? selectedMember.member_id : NO_MEMBER_ID;
    const nextId = id === NO_MEMBER_ID ? NO_MEMBER_ID : id;
    if (nextId === currentId) return;
    setActiveMember(nextId);
    // 用 currentThreadId：在 /chat 新会话刚发出首条消息时，URL 尚无 threadId
    if (currentThreadId && messages.length > 0) {
      newThreadMut.mutate({
        title: "新对话",
        memberId: nextId === NO_MEMBER_ID ? "" : nextId,
      });
    }
  }

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
    send(input, files.map((f) => f.path), sendMemberId);
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
              return <MessageBubble key={i} message={m} isStreaming={isStreamingLast} />;
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
          {/* 咨询人选择器 */}
          <div className="mb-2 flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1 text-xs font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="选择咨询人"
                title="选择本次问诊的咨询人"
              >
                {memberReady && !selectedMember ? (
                  <UserX className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                ) : (
                  <UserRound className="h-3.5 w-3.5 text-primary" aria-hidden />
                )}
                <span className="text-muted-foreground">咨询人</span>
                <span className={selectedMember ? "text-foreground" : "text-muted-foreground"}>
                  {memberLabel}
                </span>
                <ChevronDown className="h-3 w-3 text-muted-foreground" aria-hidden />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-60">
                <DropdownMenuGroup>
                  <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                    选择咨询人
                  </DropdownMenuLabel>
                  {members?.map((m) => (
                    <DropdownMenuItem
                      key={m.member_id}
                      onClick={() => handleSelectMember(m.member_id)}
                    >
                      <UserRound className="mr-2 h-3.5 w-3.5 text-primary/70" aria-hidden />
                      <span className="flex-1 truncate">
                        {m.display_name}
                        {m.is_primary && m.display_name !== "本人" ? "（本人）" : ""}
                      </span>
                      {selectedMember?.member_id === m.member_id && (
                        <Check className="h-3.5 w-3.5 text-primary" aria-hidden />
                      )}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setAddingMember(true)}>
                  <UserPlus className="mr-2 h-3.5 w-3.5" aria-hidden /> 新增咨询人
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleSelectMember(NO_MEMBER_ID)}>
                  <UserX className="mr-2 h-3.5 w-3.5" aria-hidden />
                  <span className="flex-1">不结合咨询人</span>
                  {memberReady && !selectedMember && (
                    <Check className="h-3.5 w-3.5 text-primary" aria-hidden />
                  )}
                </DropdownMenuItem>
                <p className="px-2 pb-1.5 pt-1 text-[11px] leading-snug text-muted-foreground">
                  不结合咨询人时生成通用回答，不读取也不保存任何记忆。
                </p>
              </DropdownMenuContent>
            </DropdownMenu>
            {memberReady && !selectedMember && (
              <span className="text-[11px] text-muted-foreground">通用回答 · 不读写记忆</span>
            )}
          </div>
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

          {/* 新增咨询人 */}
          <Dialog open={addingMember} onOpenChange={(o) => !o && setAddingMember(false)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>新增咨询人</DialogTitle>
              </DialogHeader>
              <p className="text-sm text-muted-foreground">
                为家人建立独立的画像与病史，问诊时按所选咨询人分别记录，互不影响。
              </p>
              <Input
                value={newMemberName}
                onChange={(e) => setNewMemberName(e.target.value)}
                placeholder="例如：母亲、父亲、孩子"
                maxLength={30}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newMemberName.trim()) {
                    createMemberMut.mutate(newMemberName.trim());
                  }
                }}
              />
              <DialogFooter>
                <Button variant="outline" onClick={() => setAddingMember(false)}>
                  取消
                </Button>
                <Button
                  disabled={!newMemberName.trim() || createMemberMut.isPending}
                  onClick={() => createMemberMut.mutate(newMemberName.trim())}
                >
                  创建
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </div>
  );
}
