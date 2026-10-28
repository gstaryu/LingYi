import { describe, it, expect } from "vitest";
import { formatHistoryInline, historyIssue } from "../profileHistory";

const YEAR = 2026;

describe("historyIssue", () => {
  it("整行为空视为合法（不录入）", () => {
    expect(historyIssue({ name: "", since_year: "", status: "active" }, YEAR)).toBeNull();
  });

  it("只有年份没有病名 → 提示补病名", () => {
    expect(historyIssue({ name: "", since_year: "2018", status: "active" }, YEAR)).toContain(
      "病名"
    );
  });

  it("年份不是 4 位数字", () => {
    expect(historyIssue({ name: "高血压", since_year: "18", status: "active" }, YEAR)).toContain(
      "4 位"
    );
  });

  it("年份超出合理范围", () => {
    expect(historyIssue({ name: "高血压", since_year: "1800", status: "active" }, YEAR)).toContain(
      "1900"
    );
    expect(historyIssue({ name: "高血压", since_year: "2099", status: "active" }, YEAR)).toContain(
      "1900"
    );
  });

  it("病名过长", () => {
    expect(
      historyIssue({ name: "x".repeat(31), since_year: "", status: "active" }, YEAR)
    ).toContain("过长");
  });

  it("合法组合返回 null（名称自动去空格）", () => {
    expect(
      historyIssue({ name: " 高血压 ", since_year: "2018", status: "history" }, YEAR)
    ).toBeNull();
  });
});

describe("formatHistoryInline", () => {
  it("空列表返回空串", () => {
    expect(formatHistoryInline()).toBe("");
    expect(formatHistoryInline([])).toBe("");
  });

  it("渲染年份与状态", () => {
    expect(
      formatHistoryInline([
        { name: "高血压", status: "active", since_year: 2018 },
        { name: "阑尾切除", status: "history" },
      ])
    ).toBe("高血压（2018 年起，现患）、阑尾切除（既往）");
  });
});
