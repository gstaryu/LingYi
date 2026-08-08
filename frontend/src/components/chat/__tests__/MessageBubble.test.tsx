import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "@/components/chat/MessageBubble";
import type { MessageItem } from "@/lib/types";

describe("MessageBubble", () => {
  it("渲染用户消息原文", () => {
    render(<MessageBubble message={{ role: "user", content: "你好，灵医" }} />);
    expect(screen.getByText("你好，灵医")).toBeInTheDocument();
  });

  it("渲染助手 Markdown（加粗）", () => {
    const msg: MessageItem = { role: "assistant", content: "**重要** 结论" };
    render(<MessageBubble message={msg} />);
    expect(screen.getByText("重要")).toBeInTheDocument();
    expect(screen.getByText("结论")).toBeInTheDocument();
  });

  it("安全警告显示警告标识", () => {
    const msg: MessageItem = { role: "assistant", content: "安全警告：附子反半夏，不可同用" };
    render(<MessageBubble message={msg} />);
    expect(screen.getByText("安全警告")).toBeInTheDocument();
  });

  it("剥离 think 标签，仅显示正式答案", () => {
    const msg: MessageItem = {
      role: "assistant",
      content: "<think>这是推理过程</think>正式辨证结论",
    };
    render(<MessageBubble message={msg} />);
    expect(screen.getByText("正式辨证结论")).toBeInTheDocument();
    expect(screen.queryByText("这是推理过程")).not.toBeInTheDocument();
  });

  it("完整 herb_names 渲染为药材 chips（非流式）", () => {
    const msg: MessageItem = {
      role: "assistant",
      content: '诊断完成\n```json\n{"herb_names": ["附子","半夏"]}\n```\n后续建议',
    };
    render(<MessageBubble message={msg} />);
    expect(screen.getByText("诊断完成")).toBeInTheDocument();
    expect(screen.getByText("后续建议")).toBeInTheDocument();
    // 药名以 chip 形式展示
    expect(screen.getByText("附子")).toBeInTheDocument();
    expect(screen.getByText("半夏")).toBeInTheDocument();
    // 处方标题存在
    expect(screen.getByText("处方")).toBeInTheDocument();
  });

  it("流式中未闭合的 herb_names JSON 被隐藏", () => {
    const msg: MessageItem = {
      role: "assistant",
      content: '辨证完成\n```json\n{"herb_names": ["附子","半',
    };
    render(<MessageBubble message={msg} isStreaming={true} />);
    expect(screen.getByText("辨证完成")).toBeInTheDocument();
    // 未闭合 JSON 不应泄漏药名
    expect(screen.queryByText("附子")).not.toBeInTheDocument();
    expect(screen.queryByText("处方")).not.toBeInTheDocument();
  });

  it("流式中未闭合代码围栏被截断", () => {
    const msg: MessageItem = {
      role: "assistant",
      content: "正常文本\n```\n未完成的代码",
    };
    render(<MessageBubble message={msg} isStreaming={true} />);
    expect(screen.getByText("正常文本")).toBeInTheDocument();
    expect(screen.queryByText("未完成的代码")).not.toBeInTheDocument();
  });

  it("【】模块标题渲染为 section 标题", () => {
    const msg: MessageItem = {
      role: "assistant",
      content: "【辨证结论】\n脾胃虚寒证",
    };
    const { container } = render(<MessageBubble message={msg} />);
    // 标题转为 h4
    const h4 = container.querySelector("h4");
    expect(h4).not.toBeNull();
    expect(h4?.textContent).toContain("辨证结论");
    expect(screen.getByText("脾胃虚寒证")).toBeInTheDocument();
  });

  it("流式空内容时显示思考中加载动画", () => {
    const msg: MessageItem = { role: "assistant", content: "" };
    render(<MessageBubble message={msg} isStreaming={true} />);
    expect(screen.getByText("思考中")).toBeInTheDocument();
  });

  it("渲染症状 Badge", () => {
    const msg: MessageItem = { role: "assistant", content: "辨证分析" };
    render(<MessageBubble message={msg} symptoms={["胃脘冷痛", "怕冷"]} />);
    expect(screen.getByText("胃脘冷痛")).toBeInTheDocument();
    expect(screen.getByText("怕冷")).toBeInTheDocument();
  });
});
