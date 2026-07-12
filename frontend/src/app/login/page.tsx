"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Leaf } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

/** 登录/注册页（Tabs 切换），成功后存 token 并跳 /chat。 */
export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [tab, setTab] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    if (!username || !password) return toast.error("请填写用户名和密码");
    setLoading(true);
    try {
      const res = await api.login(username, password);
      setAuth(res.access_token, username);
      router.replace("/chat");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister() {
    if (!username || !password) return toast.error("请填写用户名和密码");
    if (password.length < 6) return toast.error("密码至少 6 位");
    if (password !== confirm) return toast.error("两次密码不一致");
    setLoading(true);
    try {
      await api.register(username, password);
      toast.success("注册成功，正在登录...");
      const res = await api.login(username, password);
      setAuth(res.access_token, username);
      router.replace("/chat");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "注册失败");
    } finally {
      setLoading(false);
    }
  }

  const labelCls = "text-sm font-medium leading-none";

  return (
    <div className="flex flex-1 items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md shadow-lg">
        <CardHeader className="text-center space-y-3">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
            <Leaf className="h-7 w-7 text-primary" aria-hidden />
          </div>
          <CardTitle className="text-2xl">灵医 · 中医诊疗助手</CardTitle>
          <p className="text-sm text-muted-foreground">基于中医理法方药的智能诊疗对话</p>
        </CardHeader>
        <CardContent>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="login">登录</TabsTrigger>
              <TabsTrigger value="register">注册</TabsTrigger>
            </TabsList>

            <TabsContent value="login" className="space-y-4 mt-4">
              <div className="space-y-2">
                <label htmlFor="u" className={labelCls}>用户名</label>
                <Input id="u" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="请输入用户名" autoComplete="username" />
              </div>
              <div className="space-y-2">
                <label htmlFor="p" className={labelCls}>密码</label>
                <Input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="请输入密码" autoComplete="current-password" onKeyDown={(e) => e.key === "Enter" && handleLogin()} />
              </div>
              <Button className="w-full" onClick={handleLogin} disabled={loading}>
                {loading ? "登录中..." : "登录"}
              </Button>
            </TabsContent>

            <TabsContent value="register" className="space-y-4 mt-4">
              <div className="space-y-2">
                <label htmlFor="ru" className={labelCls}>用户名</label>
                <Input id="ru" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="请输入用户名" autoComplete="username" />
              </div>
              <div className="space-y-2">
                <label htmlFor="rp" className={labelCls}>密码</label>
                <Input id="rp" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少 6 位" autoComplete="new-password" />
              </div>
              <div className="space-y-2">
                <label htmlFor="rc" className={labelCls}>确认密码</label>
                <Input id="rc" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="再次输入密码" autoComplete="new-password" />
              </div>
              <Button className="w-full" onClick={handleRegister} disabled={loading}>
                {loading ? "注册中..." : "注册"}
              </Button>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
