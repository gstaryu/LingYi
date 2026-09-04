import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useChat } from "@/hooks/useChat";
import type { ChatStreamEvent, MessageItem } from "@/lib/types";

// 捕获 onEvent 注入器，供用例逐个回放事件
let emit: ((ev: ChatStreamEvent) => void) | null = null;

vi.mock("@/lib/stream", () => ({
  streamChat: vi.fn(
    (_req: unknown, opts: { onEvent: (ev: ChatStreamEvent) => void }) => {
      emit = opts.onEvent;
      return Promise.resolve();
    }
  ),
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getMessages: vi.fn(() => Promise.resolve([])),
  },
  ApiError: class ApiError extends Error {},
}));

import { api } from "@/lib/api";

describe("useChat stages 持久化", () => {
  it("token 追加不得抹掉消息上的 stages/notes（回归：spread 丢失）", async () => {
    const { result } = renderHook(() => useChat(""));

    await act(async () => {
      result.current.send("腹痛");
    });

    // 回放：阶段 -> token -> 阶段 -> done
    act(() => {
      emit?.({ type: "stage", stage: "inquiry", label: "问诊", status: "start" });
      emit?.({ type: "stage", stage: "inquiry", label: "问诊", status: "done" });
      emit?.({ type: "token", content: "诊" });
      emit?.({ type: "token", content: "断中" });
      emit?.({ type: "stage", stage: "bianzheng", label: "辨证", status: "start" });
      emit?.({
        type: "stage",
        stage: "bianzheng",
        label: "辨证",
        status: "done",
        note: { specialist: "辨证", syndrome: "脾胃虚寒" },
      });
    });

    const last = result.current.messages[result.current.messages.length - 1];
    // token 之后 stages 仍在（修复前被 {role, content} 全新对象抹掉）
    expect(last.content).toBe("诊断中");
    expect(last.stages?.map((s) => s.stage)).toEqual(["inquiry", "bianzheng"]);
    expect(last.stages?.[1]?.note?.syndrome).toBe("脾胃虚寒");

    act(() => {
      emit?.({
        type: "done",
        thread_id: "t1",
        notes: [{ specialist: "辨证" }],
        elapsed_ms: 1200,
      });
    });

    await waitFor(() => {
      const done = result.current.messages[result.current.messages.length - 1];
      expect(done.notes?.length).toBe(1);
      expect(done.elapsedMs).toBe(1200);
      // done 之后 stages 依旧完整
      expect(done.stages?.map((s) => s.stage)).toEqual(["inquiry", "bianzheng"]);
    });
  });

  it("新一轮 send 后，迟到的上一轮 resync 被丢弃（防止覆盖新一轮消息）", async () => {
    let resolveGet!: (msgs: MessageItem[]) => void;
    vi.mocked(api.getMessages).mockImplementationOnce(
      () => new Promise<MessageItem[]>((r) => (resolveGet = r))
    );

    const { result } = renderHook(() => useChat(""));
    const streams: { onEvent: (ev: ChatStreamEvent) => void }[] = [];
    const { streamChat } = await import("@/lib/stream");
    vi.mocked(streamChat).mockImplementationOnce(
      ((_req: unknown, opts: { onEvent: (ev: ChatStreamEvent) => void }) => {
        streams.push(opts);
        return Promise.resolve();
      }) as typeof streamChat
    );

    // 第 1 轮：发送 → done（触发带守卫的 resync，getMessages 挂起）
    await act(async () => {
      await result.current.send("m1");
    });
    act(() => {
      streams[0].onEvent({ type: "done", thread_id: "t1" });
    });

    // 第 2 轮开启（turnSeq 递增）
    await act(async () => {
      await result.current.send("m2");
    });

    // 迟到的 resync 此刻才 resolve，必须被丢弃
    await act(async () => {
      resolveGet([
        { role: "user", content: "m1" },
        { role: "assistant", content: "a1" },
      ]);
    });

    // 新一轮的乐观消息必须完好：4 条 = u1,a1(流式空气泡),u2,a2
    const msgs = result.current.messages;
    expect(msgs).toHaveLength(4);
    expect(msgs[2].content).toBe("m2");
    expect(msgs[3].role).toBe("assistant");
    expect(msgs[3].content).toBe("");
  });
});
