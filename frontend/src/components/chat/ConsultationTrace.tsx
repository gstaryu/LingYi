"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Loader2, Stethoscope } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import type { ConsultationNote, Stage } from "@/lib/types";

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

/** 并行专家阶段（多智能体 Send 扇出，同时执行）。 */
const SPECIALIST_STAGES = new Set(["bianzheng", "fangji", "bencao"]);

type CellStatus = "pending" | "active" | "done";

/**
 * 完成态阶段重建：图拓扑是顺序管线（并行专家簇在中间），
 * done 到达即整轮结束，因此「最后见到的阶段」之前必然全部完成。
 * 用于抵消自定义流事件偶发丢失（_emit_stage 静默吞异常）导致的摘要缺步。
 * 已见阶段的会诊笔记（note）原样保留。
 */
function reconcileStages(stages: Stage[]): Stage[] {
  const idx = new Map(STAGE_ORDER.map((s, i) => [s.stage, i]));
  const maxSeen = stages.reduce((acc, s) => Math.max(acc, idx.get(s.stage) ?? -1), -1);
  if (maxSeen < 0) return stages;
  const seen = new Map(stages.map((s) => [s.stage, s]));
  return STAGE_ORDER.slice(0, maxSeen + 1).map((s) => ({
    ...s,
    status: "done" as const,
    note: seen.get(s.stage)?.note,
  }));
}

/** 由 per-message stages 数组推导每个固定阶段的显示状态。 */
function deriveStatus(stageId: string, stages: Stage[]): CellStatus {
  const found = stages.find((s) => s.stage === stageId);
  if (!found) return "pending";
  return found.status === "done" ? "done" : "active";
}

/** 步骤状态图标：done=勾、active=旋转、pending=暗点。 */
function StepIcon({ status }: { status: CellStatus }) {
  if (status === "done") return <Check className="h-3 w-3" aria-hidden />;
  if (status === "active")
    return <Loader2 className="h-3 w-3 animate-spin" aria-hidden />;
  return <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40" aria-hidden />;
}

/** 从阶段条目中挑选一行式结论摘要（渐进揭示用），无内容返回 null。 */
function noteSummaryText(note?: ConsultationNote): string | null {
  if (!note) return null;
  if (note.syndrome) {
    const conf =
      typeof note.confidence === "number" ? ` · 置信度 ${Math.round(note.confidence * 100)}%` : "";
    return `证候：${note.syndrome}${conf}`;
  }
  if (note.recommended_formulas?.length) {
    return `推荐方：${note.recommended_formulas.join("、")}`;
  }
  if (note.safety_warnings?.length) {
    return `安全警告：${note.safety_warnings.join("；")}`;
  }
  if (note.issues?.length) {
    return `问题：${note.issues.join("；")}`;
  }
  if (note.suggestions) {
    return `建议：${note.suggestions}`;
  }
  return null;
}

/** 专家阶段完成后的单行结论卡。 */
function NoteSummaryLine({ note }: { note?: ConsultationNote }) {
  const text = noteSummaryText(note);
  if (!text) return null;
  const isWarning = Boolean(note?.safety_warnings?.length);
  return (
    <div
      className={`ml-5 truncate border-l border-primary/20 py-0.5 pl-2 text-[11px] ${
        isWarning ? "text-destructive" : "text-muted-foreground"
      }`}
      title={text}
    >
      {text}
    </div>
  );
}

/** 单个步骤行。 */
function StepRow({
  stage,
  label,
  stages,
}: {
  stage: string;
  label: string;
  stages: Stage[];
}) {
  const status = deriveStatus(stage, stages);
  const note = stages.find((s) => s.stage === stage)?.note;
  return (
    <div>
      <div
        className={`flex items-center gap-1.5 py-0.5 text-xs ${
          status === "pending" ? "text-muted-foreground/60" : "text-foreground"
        }`}
      >
        <StepIcon status={status} />
        {label}
      </div>
      {status === "done" && <NoteSummaryLine note={note} />}
    </div>
  );
}

/** 垂直步骤列表：问诊 → 并行专家簇（辨证/方剂/本草）→ 综合 → 安全审查 → 安全校验。 */
function StepList({ stages }: { stages: Stage[] }) {
  const specialists = STAGE_ORDER.filter((s) => SPECIALIST_STAGES.has(s.stage));
  const sequential = STAGE_ORDER.filter(
    (s) => !SPECIALIST_STAGES.has(s.stage) && s.stage !== "inquiry"
  );

  return (
    <div className="space-y-0.5">
      <StepRow stage="inquiry" label="问诊" stages={stages} />
      <div className="ml-1 border-l-2 border-primary/20 pl-3">
        <p className="py-0.5 text-[11px] text-muted-foreground">并行会诊</p>
        {specialists.map((s) => (
          <StepRow key={s.stage} stage={s.stage} label={s.label} stages={stages} />
        ))}
      </div>
      {sequential.map((s) => (
        <StepRow key={s.stage} stage={s.stage} label={s.label} stages={stages} />
      ))}
    </div>
  );
}

/** 字段渲染助手：仅当值非空时渲染一行。 */
function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="text-xs leading-relaxed">
      <span className="text-muted-foreground">{label}：</span>
      <span className="text-foreground">{value}</span>
    </div>
  );
}

/** 渲染单个会诊笔记。 */
function NoteCard({ note }: { note: ConsultationNote }) {
  const isReviewer =
    note.approved !== undefined ||
    (note.issues && note.issues.length > 0 && !note.syndrome);
  const specialist = note.specialist || "专家";

  return (
    <div className="rounded-md border border-border/60 bg-background/60 p-2.5">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Badge
          variant={isReviewer ? "outline" : "secondary"}
          className="text-[11px] font-normal"
        >
          {specialist}
        </Badge>
        {note.approved === true && (
          <Badge variant="secondary" className="text-[11px] text-primary">
            通过
          </Badge>
        )}
        {note.approved === false && (
          <Badge variant="secondary" className="text-[11px] text-destructive">
            未通过
          </Badge>
        )}
        {typeof note.confidence === "number" && (
          <span className="text-[11px] text-muted-foreground">
            置信度 {Math.round(note.confidence * 100)}%
          </span>
        )}
      </div>
      <Field label="证候" value={note.syndrome} />
      {note.recommended_formulas && note.recommended_formulas.length > 0 && (
        <div className="text-xs leading-relaxed">
          <span className="text-muted-foreground">推荐方剂：</span>
          <span className="text-foreground">
            {note.recommended_formulas.join("、")}
          </span>
        </div>
      )}
      {note.safety_warnings && note.safety_warnings.length > 0 && (
        <div className="text-xs leading-relaxed text-destructive">
          <span>安全警告：{note.safety_warnings.join("；")}</span>
        </div>
      )}
      {note.issues && note.issues.length > 0 && (
        <div className="text-xs leading-relaxed text-destructive">
          <span>问题：{note.issues.join("；")}</span>
        </div>
      )}
      <Field label="加减" value={note.modifications} />
      <Field label="建议" value={note.suggestions} />
      <Field label="推理" value={note.reasoning} />
    </div>
  );
}

/**
 * 会诊轨迹块（方案 A：推理轨迹）。
 *
 * - 追问/纯问诊轮（仅问诊阶段、无笔记）：流式中单行"问诊中"，完成后不渲染
 *   （答案本身即是结果，无消失问题）。
 * - 会诊轮：流式中垂直展示实时步骤（并行专家簇缩进分组）；
 *   完成后自动折叠为永久摘要条，可展开查看步骤与会诊笔记。
 */
export function ConsultationTrace({
  stages,
  notes,
  streaming = false,
  elapsedMs,
}: {
  stages?: Stage[];
  notes?: ConsultationNote[];
  streaming?: boolean;
  elapsedMs?: number;
}) {
  const hasSpecialists = (stages ?? []).some((s) => SPECIALIST_STAGES.has(s.stage));
  const [open, setOpen] = useState(false);
  const wasStreaming = useRef(streaming);

  // 流式结束自动折叠（用户仍可手动展开）
  useEffect(() => {
    if (wasStreaming.current && !streaming) setOpen(false);
    wasStreaming.current = streaming;
  }, [streaming]);

  if (!stages?.length && !notes?.length) return null;

  // 追问/纯问诊轮：流式中单行提示，完成后由答案接管
  if (!hasSpecialists && !notes?.length) {
    if (!streaming) return null;
    return (
      <div
        className="flex items-center gap-2 py-1 text-xs text-muted-foreground"
        role="status"
        aria-label="问诊中"
      >
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
        问诊中
      </div>
    );
  }

  const doneCount = reconcileStages(stages ?? []).length;
  const summaryParts = [
    `会诊过程 · ${doneCount} 步`,
    typeof elapsedMs === "number" ? `${(elapsedMs / 1000).toFixed(1)}s` : null,
    notes?.length ? `${notes.length} 位专家` : null,
  ].filter(Boolean);

  // 流式中：实时展开步骤
  if (streaming) {
    return (
      <div
        className="mb-2 rounded-md border border-border/60 bg-muted/40 px-3 py-2"
        role="status"
        aria-label="会诊进度"
        aria-live="polite"
      >
        <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-primary">
          <Stethoscope className="h-3.5 w-3.5" aria-hidden />
          多专家会诊中
        </div>
        <StepList stages={stages ?? []} />
      </div>
    );
  }

  // 完成后：折叠摘要条（永久保留，可展开）
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mb-2">
      <CollapsibleTrigger
        className="flex w-full items-center justify-between rounded-md bg-muted/60 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={open}
        aria-controls="consultation-trace-content"
      >
        <span className="flex items-center gap-1.5">
          <Stethoscope className="h-3.5 w-3.5" aria-hidden />
          {summaryParts.join(" · ")}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent id="consultation-trace-content">
        <div className="mt-1.5 space-y-1.5 pl-1">
          {stages?.length ? <StepList stages={reconcileStages(stages)} /> : null}
          {notes?.map((n, i) => (
            <NoteCard key={i} note={n} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
