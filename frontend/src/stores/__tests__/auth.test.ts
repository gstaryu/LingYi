import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/stores/auth";

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, username: null });
  });

  it("setAuth 设置 token 与 username", () => {
    useAuthStore.getState().setAuth("Bearer tok", "user1");
    expect(useAuthStore.getState().token).toBe("Bearer tok");
    expect(useAuthStore.getState().username).toBe("user1");
  });

  it("logout 清空认证状态", () => {
    useAuthStore.getState().setAuth("tok", "user1");
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().username).toBeNull();
  });
});
