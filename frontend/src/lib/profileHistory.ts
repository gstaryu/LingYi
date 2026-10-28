import type { MedicalHistoryItem } from "./types";

/** 病史编辑草稿（年份用字符串，便于留空与即时校验）。 */
export interface HistoryDraft {
  name: string;
  since_year: string;
  status: "active" | "history";
}

/** 校验单行草稿；返回中文错误提示，合法或整行为空时返回 null。 */
export function historyIssue(row: HistoryDraft, currentYear: number): string | null {
  const name = row.name.trim();
  const year = row.since_year.trim();
  if (!name && !year) return null;
  if (!name) return "病名不能为空";
  if (name.length > 30) return "病名过长（≤30 字）";
  if (year) {
    if (!/^\d{4}$/.test(year)) return "年份需为 4 位数字";
    const n = Number(year);
    if (n < 1900 || n > currentYear) return `年份需在 1900–${currentYear}`;
  }
  return null;
}

/** 病史条目 -> 侧栏摘要（"高血压（2018 年起，现患）、阑尾切除（既往）"）。 */
export function formatHistoryInline(items?: MedicalHistoryItem[]): string {
  return (items ?? [])
    .map((i) => {
      const status = i.status === "history" ? "既往" : "现患";
      return i.since_year
        ? `${i.name}（${i.since_year} 年起，${status}）`
        : `${i.name}（${status}）`;
    })
    .join("、");
}
