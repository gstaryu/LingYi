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
        </div>
        <dl className="space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">体质</dt>
            <dd>{profile?.constitution ?? "未知"}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">过敏史</dt>
            <dd className="text-right">{profile?.allergies ?? "无"}</dd>
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
    </div>
  );
}
