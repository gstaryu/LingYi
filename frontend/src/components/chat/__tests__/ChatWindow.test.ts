import { describe, it, expect } from "vitest";
import { mergeAssistantMessages } from "@/components/chat/ChatWindow";
import type { MessageItem } from "@/lib/types";

describe("mergeAssistantMessages", () => {
  it("合并连续 assistant 消息", () => {
    const msgs: MessageItem[] = [
      { role: "user", content: "症状" },
      { role: "assistant", content: "问诊回复" },
      { role: "assistant", content: "辨证结论" },
    ];
    const merged = mergeAssistantMessages(msgs);
    expect(merged).toHaveLength(2);
    expect(merged[1].content).toBe("问诊回复\n\n辨证结论");
  });

  it("连续两条含【处方建议】的 assistant 消息仅保留最后一条（重试去重）", () => {
    const msgs: MessageItem[] = [
      { role: "user", content: "腹痛" },
      {
        role: "assistant",
        content:
          "【辨证结论】\n脾胃虚寒\n\n【处方建议】\n```json\n{\"herb_names\":[\"甘草\",\"海藻\"]}\n```",
      },
      {
        role: "assistant",
        content:
          "【辨证结论】\n脾胃虚寒\n\n【处方建议】\n```json\n{\"herb_names\":[\"人参\",\"白术\"]}\n```",
      },
    ];
    const merged = mergeAssistantMessages(msgs);
    // user + one assistant (the last synthesis)
    expect(merged).toHaveLength(2);
    expect(merged[1].content).toContain("人参");
    expect(merged[1].content).not.toContain("海藻");
  });

  it("不含处方建议的连续 assistant 消息正常合并", () => {
    const msgs: MessageItem[] = [
      { role: "user", content: "问诊" },
      { role: "assistant", content: "追问：大便如何？" },
      { role: "assistant", content: "辨证中" },
    ];
    const merged = mergeAssistantMessages(msgs);
    expect(merged).toHaveLength(2);
    expect(merged[1].content).toBe("追问：大便如何？\n\n辨证中");
  });

  it("user 和 assistant 交替不合并", () => {
    const msgs: MessageItem[] = [
      { role: "user", content: "A" },
      { role: "assistant", content: "B" },
      { role: "user", content: "C" },
      { role: "assistant", content: "D" },
    ];
    const merged = mergeAssistantMessages(msgs);
    expect(merged).toHaveLength(4);
  });
});
