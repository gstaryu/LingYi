import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PrescriptionCard } from "@/components/chat/PrescriptionCard";

describe("PrescriptionCard", () => {
  it("空药材列表不渲染", () => {
    const { container } = render(<PrescriptionCard herbs={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("渲染药名 chips", () => {
    render(<PrescriptionCard herbs={["人参", "白术"]} />);
    expect(screen.getByText("人参")).toBeInTheDocument();
    expect(screen.getByText("白术")).toBeInTheDocument();
    expect(screen.getByText("处方")).toBeInTheDocument();
  });

  it("从'药名（3-9g）'拆分药名与剂量", () => {
    render(<PrescriptionCard herbs={["人参（3-9g）"]} />);
    expect(screen.getByText("人参")).toBeInTheDocument();
    expect(screen.getByText("3-9g")).toBeInTheDocument();
  });

  it("从'药名 9g'拆分药名与剂量", () => {
    render(<PrescriptionCard herbs={["白术 9g"]} />);
    expect(screen.getByText("白术")).toBeInTheDocument();
    expect(screen.getByText("9g")).toBeInTheDocument();
  });

  it("自定义标题", () => {
    render(<PrescriptionCard herbs={["甘草"]} title="组成" />);
    expect(screen.getByText("组成")).toBeInTheDocument();
  });

  it("重复药名去重（synthesis 重试残留防护）", () => {
    render(<PrescriptionCard herbs={["甘草", "海藻", "甘草", "白术"]} />);
    // 甘草只出现一次（chip 文本）
    const gancaoChips = screen.getAllByText("甘草");
    expect(gancaoChips).toHaveLength(1);
    expect(screen.getByText("白术")).toBeInTheDocument();
    expect(screen.getByText("海藻")).toBeInTheDocument();
  });

  it("从处方正文（rawText）中查找药名对应剂量", () => {
    render(
      <PrescriptionCard
        herbs={["人参", "白术", "干姜"]}
        rawText="治以温中散寒，方用理中丸加减：人参（3-9g） 白术（6-12g） 干姜 3-10g。"
      />
    );
    expect(screen.getByText("人参")).toBeInTheDocument();
    expect(screen.getByText("3-9g")).toBeInTheDocument();
    expect(screen.getByText("白术")).toBeInTheDocument();
    expect(screen.getByText("6-12g")).toBeInTheDocument();
    expect(screen.getByText("干姜")).toBeInTheDocument();
    expect(screen.getByText("3-10g")).toBeInTheDocument();
  });

  it("rawText 中无剂量时仅显示药名", () => {
    render(<PrescriptionCard herbs={["甘草"]} rawText="方用炙甘草汤" />);
    expect(screen.getByText("甘草")).toBeInTheDocument();
    // 不应有剂量元素
    expect(screen.queryByText(/^\d+[-~]\d+g$/)).not.toBeInTheDocument();
  });
});
