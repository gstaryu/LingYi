"use client";

import { Check, Loader2 } from "lucide-react";
import type { Stage } from "@/lib/types";

/** 固定阶段顺序（与后端 graph_multiagent STAGE_LABELS 一致）。 */
const STAGE_ORDER: { stage: string; label: string }[] = [
  { stage: "inquiry", label: "问诊" },
  { stage: "bianzheng", label: "辨证" },
  { stage: "fangji", label: "方剂" },
  { stage: "bencao", label: "本草" },
  { stage: "synthesis", label: "综合" },
  { stage: "reviewer", label: "安全审查" },
  { stage: "safety_check", label: "安全校验" },
];

type CellStatus = "pending" | "active" | "done";

/** 由实时 stages 数组推导每个固定阶段的显示状态。 */
function deriveStatus(stageId: string, stages: Stage[]): CellStatus {
  const found = stages.find((s) => s.stage === stageId);
  if (!found) return "pending";
  return found.status === "done" ? "done" : "active";
}

export function ConsultationTimeline({
  stages,
  streaming,
}: {
  stages: Stage[];
  streaming: boolean;
}) {
  // 无任何阶段进度且非流式时不渲染
  if (stages.length === 0 && !streaming) return null;

  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      role="status"
      aria-label="会诊进度"
      aria-live="polite"
    >
      {STAGE_ORDER.map((s, i) => {
        const status = deriveStatus(s.stage, stages);
        const isLast = i === STAGE_ORDER.length - 1;
        return (
          <div key={s.stage} className="flex items-center gap-1.5">
            <span
              className={[
                "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition-colors",
                status === "pending"
                  ? "bg-muted text-muted-foreground"
                  : status === "active"
                    ? "bg-primary text-primary-foreground shadow-sm ring-2 ring-primary/30 animate-pulse"
                    : "bg-primary/15 text-primary",
              ].join(" ")}
            >
              {status === "done" ? (
                <Check className="h-3 w-3" aria-hidden />
              ) : status === "active" ? (
                <Loader2
                  className="h-3 w-3 animate-spin"
                  aria-hidden
                />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-current opacity-50" aria-hidden />
              )}
              {s.label}
            </span>
            {!isLast && <span className="text-muted-foreground/40" aria-hidden>·</span>}
          </div>
        );
      })}
    </div>
  );
}
