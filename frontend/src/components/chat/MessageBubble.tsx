"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Copy, Check, Loader2 } from "lucide-react";
import type { MessageItem } from "@/lib/types";
import type { Components } from "react-markdown";
import { PrescriptionCard } from "./PrescriptionCard";

/** 提取完整的 herb_names JSON，返回药材列表与剥离 JSON 后的文本。 */
function extractHerbs(s: string): { text: string; herbs: string[] } {
  const herbs: string[] = [];
  // 1. ```json {"herb_names":[...]} ``` 代码块
  let text = s.replace(/```(?:json)?\s*(\{[\s\S]*?"herb_names"[\s\S]*?\})\s*```/g, (_m, j) => {
    try {
      const data = JSON.parse(j);
      if (Array.isArray(data.herb_names)) herbs.push(...data.herb_names);
    } catch {
      /* 忽略解析失败 */
    }
    return "";
  });
  // 2. 行内 {"herb_names":[...]} 对象
  text = text.replace(/\{[^{}]*"herb_names"[^{}]*\}/g, (m) => {
    try {
      const data = JSON.parse(m);
      if (Array.isArray(data.herb_names)) herbs.push(...data.herb_names);
    } catch {
      /* 忽略 */
    }
    return "";
  });
  return { text, herbs };
}

/**
 * 清理助手输出：剥离 think 标签、提取 herb_names、流式感知隐藏未闭合片段。
 *
 * isStreaming=true 时，若存在未闭合的 ``` 围栏（奇数个）或不完整的
 * {"herb_names" 缺少闭合 }，则截断尾部，避免部分 JSON/围栏闪烁。
 */
function processContent(
  content: string,
  isStreaming = false
): { text: string; herbs: string[] } {
  let s = content;
  // 1. 剥离 think 标签：只保留最后一个 </think...> 之后的正式答案
  const idx = s.lastIndexOf("</think");
  if (idx !== -1) {
    const gt = s.indexOf(">", idx);
    s = gt !== -1 ? s.slice(gt + 1) : "";
  }

  // 2. 提取完整 herb_names（已闭合的 JSON 块/对象）
  const { text: withoutHerbs, herbs } = extractHerbs(s);
  s = withoutHerbs;

  // 3. 流式感知：隐藏尾部未闭合的围栏 / herb_names JSON
  if (isStreaming) {
    // 未闭合代码围栏（奇数个 ```）-> 截断到最后一个 ```
    const fences = s.match(/```/g);
    if (fences && fences.length % 2 === 1) {
      const lastFence = s.lastIndexOf("```");
      s = s.slice(0, lastFence);
    }
    // 未闭合的 {"herb_names" 缺少 } -> 截断
    const herbStart = s.lastIndexOf('{"herb_names"');
    if (herbStart !== -1 && !s.slice(herbStart).includes("}")) {
      s = s.slice(0, herbStart);
    }
    // 流式中可能残留未闭合 ```json 围栏（无闭合 ```），再次清理
    const openJson = s.match(/```(?:json)?\s*\{[\s\S]*$/);
    if (openJson && !openJson[0].includes("```", 3)) {
      s = s.slice(0, s.length - openJson[0].length);
    }
  }

  // 4. 【】模块标题转为 H4 以便自定义 section 样式
  s = s.replace(/^【([^】]+)】\s*/gm, "#### 【$1】\n");

  // 5. 残余多余空行收敛
  s = s.replace(/\n{3,}/g, "\n\n").replace(/^\n+/, "").trim();

  // 6. 剂量范围中的 ASCII 波浪号 ~ 统一替换为全角 ～
  //    防止 remark-gfm 把成对的单波浪号（如 "3~10g" ... "6~12g"）误解为删除线
  s = s.replace(/~/g, "～");
  return { text: s, herbs };
}

/** Markdown 各元素的自定义样式（TCM 设计令牌，免 typography 插件）。 */
const mdComponents: Components = {
  h1: ({ children }) => (
    <h1 className="mt-3 mb-2 font-[family-name:var(--font-serif)] text-base font-semibold text-foreground">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-3 mb-2 border-t border-border/60 pt-2 font-[family-name:var(--font-serif)] text-base font-semibold text-foreground">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-2.5 mb-1.5 font-[family-name:var(--font-serif)] text-sm font-semibold text-foreground">
      {children}
    </h3>
  ),
  // 【...】模块标题 -> 带上边框的衬线 section 标题
  h4: ({ children }) => (
    <h4 className="mt-3 mb-1.5 border-t border-primary/20 pt-2 font-[family-name:var(--font-serif)] text-sm font-semibold text-primary">
      {children}
    </h4>
  ),
  p: ({ children }) => <p className="my-2 leading-[1.7]">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5 leading-[1.7]">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5 leading-[1.7]">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-primary/40 pl-3 text-muted-foreground">
      {children}
    </blockquote>
  ),
  code: ({ className, children }) => (
    <code className={`${className ?? ""} rounded bg-background/60 px-1 py-0.5 font-mono text-xs`}>
      {children}
    </code>
  ),
};

export function MessageBubble({
  message,
  symptoms,
  isStreaming = false,
}: {
  message: MessageItem;
  symptoms?: string[];
  isStreaming?: boolean;
}) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const { text: cleaned, herbs } = processContent(message.content, isStreaming);
  const isSafety = !isUser && cleaned.includes("安全警告");

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* 剪贴板不可用 */
    }
  }

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-primary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="group flex justify-start">
      <div
        className={`max-w-[85%] rounded-2xl rounded-bl-sm px-4 py-3 ${
          isSafety ? "border border-destructive/40 bg-destructive/10" : "bg-muted"
        }`}
      >
        {isSafety && (
          <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-destructive">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            安全警告
          </div>
        )}
        <div className="max-w-[65ch] text-sm">
          {cleaned ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {cleaned}
            </ReactMarkdown>
          ) : (
            isStreaming && (
              <div className="flex items-center gap-2 py-1 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                <span className="animate-pulse text-sm">思考中</span>
              </div>
            )
          )}
        </div>
        {herbs.length > 0 && <PrescriptionCard herbs={herbs} rawText={cleaned} />}
        {symptoms && symptoms.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {symptoms.map((s) => (
              <Badge key={s} variant="secondary" className="text-xs font-normal">
                {s}
              </Badge>
            ))}
          </div>
        )}
      </div>
      {!isStreaming && cleaned && (
        <button
          onClick={handleCopy}
          className="ml-1 mt-1 self-start rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
          aria-label="复制回复"
          title="复制"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-primary" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}
