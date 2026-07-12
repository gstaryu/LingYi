"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth";

/** 根路由：已登录跳 /chat，未登录跳 /login。 */
export default function Home() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    // 等 zustand persist 水合后再判断，避免闪烁
    router.replace(token ? "/chat" : "/login");
  }, [token, router]);

  return (
    <div className="flex flex-1 items-center justify-center text-muted-foreground">
      正在跳转...
    </div>
  );
}
