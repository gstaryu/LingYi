"use client";

import { Leaf } from "lucide-react";

/**
 * 处方卡片 - 以朱砂强调色左边框展示药材 chips。
 *
 * 解析药材条目中的剂量（如 "人参（3-9g）" / "白术 9g"），
 * 将药名与剂量分开展示：药名加粗，剂量弱化。
 * 若 herb_names JSON 仅含药名（无剂量），则从处方正文（rawText）中
 * 匹配药名后的剂量模式（如 "干姜 3-10g" / "干姜（3-10g）"）。
 */

interface HerbChip {
  name: string;
  dosage: string;
}

/** 从单条药材文本中拆分药名与剂量。 */
function parseHerb(raw: string): HerbChip {
  const s = raw.trim();
  if (!s) return { name: "", dosage: "" };
  // 匹配 "药名（3-9g）" / "药名(3-9g)" / "药名 3-9g" / "药名3-9g" / "药名 9g"
  const m = s.match(/^(.+?)\s*[（(]?\s*(\d[\d.\-~～至]*\s*[gｇ克ml]*)\s*[)）]?\s*$/);
  if (m) {
    return { name: m[1].trim(), dosage: m[2].trim() };
  }
  return { name: s, dosage: "" };
}

/** 从处方正文中查找指定药名后的剂量（如 "干姜（3-10g）" / "干姜 3-10g" / "干姜3-10g"）。 */
function findDosageInText(herbName: string, text: string): string {
  if (!herbName || !text) return "";
  // 转义药名中的正则特殊字符
  const escaped = herbName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // 匹配药名后紧跟的剂量：可选括号 + 数字范围 + 单位
  const m = text.match(
    new RegExp(
      escaped + "\\s*[（(]?\\s*(\\d[\\d.\\-~～至]*\\s*(?:g|ｇ|克|ml))\\s*[)）]?"
    )
  );
  return m ? m[1].trim() : "";
}

export function PrescriptionCard({
  herbs,
  title = "处方",
  rawText = "",
}: {
  herbs: string[];
  title?: string;
  rawText?: string;
}) {
  if (!herbs || herbs.length === 0) return null;
  // Dedup by herb name (first occurrence wins) - guards against duplicate
  // herb_names JSON blocks when synthesis retries leave stale content.
  const seen = new Set<string>();
  const chips = herbs
    .map((raw) => {
      const parsed = parseHerb(raw);
      // 若 herb_names JSON 只含药名（无剂量），从处方正文中查找
      if (!parsed.dosage && parsed.name && rawText) {
        return { name: parsed.name, dosage: findDosageInText(parsed.name, rawText) };
      }
      return parsed;
    })
    .filter((c) => c.name)
    .filter((c) => {
      if (seen.has(c.name)) return false;
      seen.add(c.name);
      return true;
    });

  return (
    <div
      className="mt-3 rounded-lg border-l-[3px] border-accent bg-accent/5 px-4 py-3"
      role="region"
      aria-label={title}
    >
      <div className="mb-2 flex items-center gap-1.5 font-[family-name:var(--font-serif)] text-sm font-semibold text-foreground">
        <Leaf className="h-4 w-4 text-accent" aria-hidden />
        {title}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {chips.map((c, i) => (
          <span
            key={`${c.name}-${i}`}
            className="inline-flex items-baseline gap-1 rounded-md border border-border/60 bg-background/80 px-2 py-1 text-xs"
          >
            <span className="font-medium text-foreground">{c.name}</span>
            {c.dosage && (
              <span className="text-muted-foreground tabular-nums">{c.dosage}</span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}
