import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn (类名合并)", () => {
  it("合并多个类名", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("跳过 falsy 值", () => {
    expect(cn("a", false && "b", undefined, null, "c")).toBe("a c");
  });

  it("tailwind-merge 去重冲突类", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
  });
});
