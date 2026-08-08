import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConsultationTimeline } from "@/components/chat/ConsultationTimeline";
import type { Stage } from "@/lib/types";

describe("ConsultationTimeline", () => {
  it("无阶段且非流式时不渲染", () => {
    const { container } = render(
      <ConsultationTimeline stages={[]} streaming={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("流式时渲染全部 7 个阶段标签", () => {
    render(<ConsultationTimeline stages={[]} streaming={true} />);
    for (const label of ["问诊", "辨证", "方剂", "本草", "综合", "安全审查", "安全校验"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("start 阶段显示为 active（含旋转加载图标）", () => {
    const stages: Stage[] = [
      { stage: "inquiry", label: "问诊", status: "start" },
    ];
    const { container } = render(
      <ConsultationTimeline stages={stages} streaming={true} />
    );
    // 旋转加载图标存在
    const spinner = container.querySelector("svg.animate-spin");
    expect(spinner).not.toBeNull();
  });

  it("done 阶段显示为完成（无旋转图标）", () => {
    const stages: Stage[] = [
      { stage: "inquiry", label: "问诊", status: "done" },
      { stage: "bianzheng", label: "辨证", status: "start" },
    ];
    const { container } = render(
      <ConsultationTimeline stages={stages} streaming={true} />
    );
    // 仅辨证 active，问诊 done -> 只有 1 个 spinner
    const spinners = container.querySelectorAll("svg.animate-spin");
    expect(spinners.length).toBe(1);
  });

  it("全部 done 时无旋转图标", () => {
    const stages: Stage[] = [
      { stage: "inquiry", label: "问诊", status: "done" },
      { stage: "synthesis", label: "综合", status: "done" },
    ];
    const { container } = render(
      <ConsultationTimeline stages={stages} streaming={false} />
    );
    expect(container.querySelectorAll("svg.animate-spin").length).toBe(0);
  });
});
