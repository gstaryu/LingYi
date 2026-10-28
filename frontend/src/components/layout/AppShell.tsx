"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
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
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import {
  Plus,
  MoreVertical,
  Pencil,
  Trash2,
  LogOut,
  Leaf,
  HeartPulse,
} from "lucide-react";
import type { ProfileUpdate } from "@/lib/types";
import {
  formatHistoryInline,
  historyIssue,
  type HistoryDraft,
} from "@/lib/profileHistory";

/** 应用外壳：路由守卫 + 侧边栏（会话/画像）+ 主区域。 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { token, username, logout } = useAuthStore();
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => setHydrated(true), []);
  useEffect(() => {
    if (hydrated && !token) router.replace("/login");
  }, [hydrated, token, router]);

  if (!hydrated || !token) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        加载中...
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <aside className="hidden w-72 flex-col border-r bg-sidebar md:flex">
        <SidebarContent
          username={username ?? ""}
          pathname={pathname}
          onLogout={() => {
            logout();
            router.replace("/login");
          }}
        />
      </aside>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</main>
    </div>
  );
}

function SidebarContent({
  username,
  pathname,
  onLogout,
}: {
  username: string;
  pathname: string;
  onLogout: () => void;
}) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: threads } = useQuery({
    queryKey: ["threads"],
    queryFn: api.listThreads,
  });
  const { data: profile } = useQuery({
    queryKey: ["profile", username],
    queryFn: () => api.getProfile(username),
    enabled: !!username,
  });

  const createMut = useMutation({
    mutationFn: () => api.createThread("新对话"),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["threads"] });
      router.push(`/chat/${t.thread_id}`);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "创建失败"),
  });

  const renameMut = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.renameThread(id, title),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["threads"] }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "重命名失败"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteThread(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["threads"] }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "删除失败"),
  });

  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({
    allergies: "",
    age: "",
    gender: "",
  });
  const [historyDraft, setHistoryDraft] = useState<HistoryDraft[]>([]);
  const currentYear = new Date().getFullYear();
  const hasHistoryIssue = historyDraft.some((r) => historyIssue(r, currentYear) !== null);

  const updateProfileMut = useMutation({
    mutationFn: ({ user, data }: { user: string; data: ProfileUpdate }) =>
      api.updateProfile(user, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile", username] });
      toast.success("画像已更新");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "更新失败"),
  });

  return (
    <div className="flex h-full flex-col">
      {/* 顶部：Logo + 新建 */}
      <div className="flex items-center gap-2 p-3">
        <Leaf className="h-5 w-5 text-primary" aria-hidden />
        <span className="font-semibold">灵医</span>
        <Button
          size="sm"
          className="ml-auto"
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending}
        >
          <Plus className="mr-1 h-4 w-4" /> 新对话
        </Button>
      </div>
      <Separator />

      {/* 会话列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-0.5 p-2">
          {threads?.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">暂无会话</p>
          )}
          {threads?.map((t) => {
            const active = pathname === `/chat/${t.thread_id}`;
            return (
              <div
                key={t.thread_id}
                className={`group flex items-center rounded-md px-2 py-1.5 ${
                  active ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/60"
                }`}
              >
                <button
                  className="flex-1 truncate text-left text-sm"
                  onClick={() => router.push(`/chat/${t.thread_id}`)}
                >
                  {t.title || "新对话"}
                </button>
                <DropdownMenu>
                  <DropdownMenuTrigger
                    className="rounded p-1 opacity-0 hover:bg-background group-hover:opacity-100"
                    aria-label="会话操作"
                  >
                    <MoreVertical className="h-3.5 w-3.5" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      onClick={() => {
                        setRenaming({ id: t.thread_id, title: t.title || "新对话" });
                        setNewTitle(t.title || "新对话");
                      }}
                    >
                      <Pencil className="mr-2 h-3.5 w-3.5" /> 重命名
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={() => setDeleting(t.thread_id)}
                    >
                      <Trash2 className="mr-2 h-3.5 w-3.5" /> 删除
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            );
          })}
        </div>
      </div>
      <Separator />

      {/* 画像 */}
      <div className="p-3">
        <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <HeartPulse className="h-3.5 w-3.5" aria-hidden /> 用户画像
          <button
            className="ml-auto rounded p-0.5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => {
              setProfileForm({
                allergies: profile?.allergies ?? "无",
                age: profile?.age != null ? String(profile.age) : "",
                gender: profile?.gender ?? "",
              });
              setHistoryDraft(
                (profile?.medical_history ?? []).map((i) => ({
                  name: i.name,
                  since_year: i.since_year ? String(i.since_year) : "",
                  status: i.status === "history" ? "history" : "active",
                }))
              );
              setEditingProfile(true);
            }}
            aria-label="编辑画像"
            title="编辑画像"
          >
            <Pencil className="h-3 w-3" />
          </button>
        </div>
        <dl className="space-y-1 text-sm">
          <div className="flex justify-between gap-2">
            <dt className="shrink-0 text-muted-foreground">年龄/性别</dt>
            <dd className="truncate text-right">
              {profile?.age != null ? `${profile.age} 岁` : "—"}
              {profile?.gender === "male" ? " · 男" : profile?.gender === "female" ? " · 女" : ""}
            </dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="shrink-0 text-muted-foreground">体质</dt>
            <dd className="truncate text-right">{profile?.constitution ?? "未知"}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="shrink-0 text-muted-foreground">过敏史</dt>
            <dd className="min-w-0 truncate text-right">{profile?.allergies ?? "无"}</dd>
          </div>
          <div className="flex justify-between gap-2">
            <dt className="shrink-0 text-muted-foreground">既往病史</dt>
            <dd className="min-w-0 truncate text-right">
              {formatHistoryInline(profile?.medical_history) || "—"}
            </dd>
          </div>
        </dl>
      </div>
      <Separator />

      {/* 用户/登出 */}
      <div className="flex items-center gap-2 p-3">
        <Avatar className="h-8 w-8">
          <AvatarFallback className="bg-primary/10 text-xs text-primary">
            {username.slice(0, 1).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        <span className="flex-1 truncate text-sm">{username}</span>
        <Button variant="ghost" size="icon" onClick={onLogout} aria-label="登出" title="登出">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>

      {/* 重命名对话框 */}
      <Dialog open={!!renaming} onOpenChange={(o) => !o && setRenaming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名会话</DialogTitle>
          </DialogHeader>
          <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="会话标题" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenaming(null)}>
              取消
            </Button>
            <Button
              onClick={() => {
                if (renaming && newTitle.trim()) {
                  renameMut.mutate({ id: renaming.id, title: newTitle.trim() });
                  setRenaming(null);
                }
              }}
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除会话？</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">删除后无法恢复，确定继续吗？</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleting) {
                  deleteMut.mutate(deleting);
                  if (pathname === `/chat/${deleting}`) router.push("/chat");
                  setDeleting(null);
                }
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 编辑画像 */}
      <Dialog open={editingProfile} onOpenChange={(o) => !o && setEditingProfile(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑画像</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground" htmlFor="pf-age">
                年龄
              </label>
              <Input
                id="pf-age"
                inputMode="numeric"
                value={profileForm.age}
                onChange={(e) => setProfileForm((f) => ({ ...f, age: e.target.value }))}
                placeholder="如：32（留空表示不修改）"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground" htmlFor="pf-gender">
                性别
              </label>
              <select
                id="pf-gender"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={profileForm.gender}
                onChange={(e) => setProfileForm((f) => ({ ...f, gender: e.target.value }))}
              >
                <option value="">未设置</option>
                <option value="male">男</option>
                <option value="female">女</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground" htmlFor="pf-allergies">
                过敏史
              </label>
              <Input
                id="pf-allergies"
                value={profileForm.allergies}
                onChange={(e) => setProfileForm((f) => ({ ...f, allergies: e.target.value }))}
                placeholder="如：青霉素、海鲜；输入「无」表示无过敏"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">既往病史</span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={() =>
                    setHistoryDraft((rows) => [
                      ...rows,
                      { name: "", since_year: "", status: "active" as const },
                    ])
                  }
                >
                  <Plus className="mr-1 h-3 w-3" /> 添加
                </Button>
              </div>
              {historyDraft.length === 0 && (
                <p className="text-[11px] text-muted-foreground">
                  暂无记录，可点「添加」录入慢性病、手术史等。
                </p>
              )}
              <div className="space-y-2">
                {historyDraft.map((row, idx) => {
                  const issue = historyIssue(row, currentYear);
                  return (
                    <div key={idx} className="space-y-1">
                      <div className="flex items-center gap-1.5">
                        <Input
                          value={row.name}
                          placeholder="病名，如 高血压"
                          aria-label={`病史名称 ${idx + 1}`}
                          className="h-8 flex-1 text-sm"
                          onChange={(e) =>
                            setHistoryDraft((rows) =>
                              rows.map((r, i) => (i === idx ? { ...r, name: e.target.value } : r))
                            )
                          }
                        />
                        <Input
                          value={row.since_year}
                          placeholder="年份"
                          inputMode="numeric"
                          aria-label={`病史年份 ${idx + 1}`}
                          className="h-8 w-20 text-sm"
                          onChange={(e) =>
                            setHistoryDraft((rows) =>
                              rows.map((r, i) =>
                                i === idx ? { ...r, since_year: e.target.value } : r
                              )
                            )
                          }
                        />
                        <select
                          value={row.status}
                          aria-label={`病史状态 ${idx + 1}`}
                          className="h-8 rounded-md border border-input bg-background px-1.5 text-sm"
                          onChange={(e) =>
                            setHistoryDraft((rows) =>
                              rows.map((r, i) =>
                                i === idx
                                  ? { ...r, status: e.target.value as HistoryDraft["status"] }
                                  : r
                              )
                            )
                          }
                        >
                          <option value="active">现患</option>
                          <option value="history">既往</option>
                        </select>
                        <button
                          type="button"
                          aria-label={`删除病史 ${idx + 1}`}
                          className="rounded p-1 text-muted-foreground hover:text-destructive"
                          onClick={() =>
                            setHistoryDraft((rows) => rows.filter((_, i) => i !== idx))
                          }
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      {issue && <p className="text-[11px] text-destructive">{issue}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingProfile(false)}>
              取消
            </Button>
            <Button
              disabled={updateProfileMut.isPending || hasHistoryIssue}
              onClick={() => {
                const data: ProfileUpdate = {
                  allergies: profileForm.allergies.trim() || "无",
                  gender: profileForm.gender,
                  medical_history: historyDraft
                    .filter((r) => r.name.trim())
                    .map((r) => ({
                      name: r.name.trim(),
                      status: r.status,
                      since_year: r.since_year.trim() ? Number(r.since_year.trim()) : null,
                      note: "",
                    })),
                };
                const ageNum = Number(profileForm.age.trim());
                if (
                  profileForm.age.trim() &&
                  Number.isFinite(ageNum) &&
                  ageNum > 0 &&
                  ageNum < 130
                ) {
                  data.age = Math.round(ageNum);
                }
                updateProfileMut.mutate({ user: username, data });
                setEditingProfile(false);
              }}
            >
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
