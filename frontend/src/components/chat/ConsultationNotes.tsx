"use client";

import { useState } from "react";
import { ChevronDown, Stethoscope } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import type { ConsultationNote } from "@/lib/types";

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
  const isReviewer = note.approved !== undefined || (note.issues && note.issues.length > 0 && !note.syndrome);
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
          <Badge variant="secondary" className="text-[11px] text-primary">通过</Badge>
        )}
        {note.approved === false && (
          <Badge variant="secondary" className="text-[11px] text-destructive">未通过</Badge>
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
          <span className="text-foreground">{note.recommended_formulas.join("、")}</span>
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

export function ConsultationNotes({ notes }: { notes: ConsultationNote[] }) {
  const [open, setOpen] = useState(false);
  if (!notes || notes.length === 0) return null;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mt-2">
      <CollapsibleTrigger
        className="flex w-full items-center justify-between rounded-md bg-muted/60 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={open}
        aria-controls="consultation-notes-content"
      >
        <span className="flex items-center gap-1.5">
          <Stethoscope className="h-3.5 w-3.5" aria-hidden />
          会诊过程（{notes.length} 位专家）
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent id="consultation-notes-content">
        <div className="mt-1.5 space-y-1.5 pl-1">
          {notes.map((n, i) => (
            <NoteCard key={i} note={n} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
