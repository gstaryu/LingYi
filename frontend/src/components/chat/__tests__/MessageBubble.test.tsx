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
    // 警告头（exact 匹配）
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

  it("隐藏 herb_names JSON 代码块", () => {
    const msg: MessageItem = {
      role: "assistant",
      content: '诊断完成\n```json\n{"herb_names": ["附子","半夏"]}\n```\n后续建议',
    };
    render(<MessageBubble message={msg} />);
    expect(screen.getByText("诊断完成")).toBeInTheDocument();
    expect(screen.getByText("后续建议")).toBeInTheDocument();
    expect(screen.queryByText("附子")).not.toBeInTheDocument();
  });

  it("渲染症状 Badge", () => {
    const msg: MessageItem = { role: "assistant", content: "辨证分析" };
    render(<MessageBubble message={msg} symptoms={["胃脘冷痛", "怕冷"]} />);
    expect(screen.getByText("胃脘冷痛")).toBeInTheDocument();
    expect(screen.getByText("怕冷")).toBeInTheDocument();
  });
});
