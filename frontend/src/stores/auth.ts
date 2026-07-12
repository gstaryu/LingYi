"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * 认证状态（Zustand + persist）。
 * token/username 持久化到 localStorage，刷新页面后保持登录。
 */

interface AuthState {
  token: string | null;
  username: string | null;
  setAuth: (token: string, username: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      setAuth: (token, username) => set({ token, username }),
      logout: () => set({ token: null, username: null }),
    }),
    { name: "lingyi-auth" }
  )
);
