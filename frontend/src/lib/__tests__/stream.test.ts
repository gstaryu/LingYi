import { describe, it, expect, vi, beforeEach } from "vitest";
import { streamChat } from "@/lib/stream";
import { useAuthStore } from "@/stores/auth";
import type { ChatStreamEvent } from "@/lib/types";

/** 构造 SSE 响应流（data: {json}\n\n）。 */
function makeSSEStream(events: object[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  return new ReadableStream({
    start(controller) {
      controller.enqueue(enc.encode(body));
      controller.close();
    },
  });
}

describe("streamChat (SSE 解析)", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: "tok" });
    vi.unstubAllGlobals();
  });

  it("按序解析 token 与 done 事件", async () => {
    const events: ChatStreamEvent[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: makeSSEStream([
          { token: "你好" },
          { token: "世界" },
          { done: true, thread_id: "t-123" },
        ]),
      })
    );
    await streamChat({ message: "hi" }, { onEvent: (e) => events.push(e) });
    expect(events.map((e) => e.type)).toEqual(["token", "token", "done"]);
    expect((events[0] as { content: string }).content).toBe("你好");
    expect((events[2] as { thread_id: string }).thread_id).toBe("t-123");
  });

  it("解析 error 事件", async () => {
    const events: ChatStreamEvent[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: makeSSEStream([{ error: "处理失败" }]),
      })
    );
    await streamChat({ message: "hi" }, { onEvent: (e) => events.push(e) });
    expect(events[0]).toEqual({ type: "error", message: "处理失败" });
  });

  it("解析 stage 阶段进度事件", async () => {
    const events: ChatStreamEvent[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: makeSSEStream([
          { type: "stage", stage: "bianzheng", label: "辨证", status: "start" },
          { type: "stage", stage: "bianzheng", label: "辨证", status: "done" },
        ]),
      })
    );
    await streamChat({ message: "hi" }, { onEvent: (e) => events.push(e) });
    expect(events.map((e) => e.type)).toEqual(["stage", "stage"]);
    expect(events[0]).toEqual({
      type: "stage",
      stage: "bianzheng",
      label: "辨证",
      status: "start",
    });
    expect((events[1] as { status: string }).status).toBe("done");
  });

  it("done 事件携带 notes 会诊笔记", async () => {
    const events: ChatStreamEvent[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        body: makeSSEStream([
          { done: true, thread_id: "t-9", notes: [{ specialist: "辨证", syndrome: "脾胃虚寒" }] },
        ]),
      })
    );
    await streamChat({ message: "hi" }, { onEvent: (e) => events.push(e) });
    const done = events[0] as { type: string; thread_id: string; notes?: unknown[] };
    expect(done.type).toBe("done");
    expect(done.thread_id).toBe("t-9");
    expect(Array.isArray(done.notes)).toBe(true);
    expect((done.notes as [{ specialist: string }])[0].specialist).toBe("辨证");
  });

  it("请求失败时触发 onError", async () => {
    let errMsg = "";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, body: null })
    );
    await streamChat(
      { message: "hi" },
      { onEvent: () => {}, onError: (e) => (errMsg = e.message) }
    );
    expect(errMsg).toContain("500");
  });
});
