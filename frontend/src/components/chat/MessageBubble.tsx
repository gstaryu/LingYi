"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle } from "lucide-react";
import type { MessageItem } from "@/lib/types";
import type { Components } from "react-markdown";

/** 清理助手输出：剥离 think 标签、隐藏 herb_names JSON、【】模块前强制换行。 */
function cleanContent(content: string): string {
  let s = content;
  // 1. 剥离 think 标签（doubao 等模型会泄漏推理过程）：只保留最后一个 </think...> 之后的正式答案
  const idx = s.lastIndexOf("</think");
  if (idx !== -1) {
    const gt = s.indexOf(">", idx);
    s = gt !== -1 ? s.slice(gt + 1) : "";
  }
  // 2. 隐藏 herb_names JSON 代码块（仅后台安全校验用）
  s = s
    .replace(/```json\s*\{[\s\S]*?"herb_names"[\s\S]*?\}\s*```/g, "")
    .replace(/\{[^{}]*"herb_names"[^{}]*\}/g, "");
  // 3. 【】模块前强制换行（LLM 常把多个模块挤在一行）
  s = s.replace(/【/g, "\n【").replace(/\n{3,}/g, "\n\n").replace(/^\n+/, "");
  return s.trim();
}

/** Markdown 各元素的自定义样式（免 @tailwindcss/typography 依赖）。 */
const mdComponents: Components = {
  h1: ({ children }) => <h1 className="text-lg font-semibold mt-3 mb-2">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-semibold mt-3 mb-2">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>,
  p: ({ children }) => <p className="leading-relaxed my-1.5">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 my-1.5 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 my-1.5 space-y-1">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-primary/40 pl-3 my-2 text-muted-foreground">{children}</blockquote>
  ),
  code: ({ className, children }) => (
    <code className={`${className ?? ""} rounded bg-background/60 px-1 py-0.5 text-xs font-mono`}>{children}</code>
  ),
};

export function MessageBubble({
  message,
  symptoms,
}: {
  message: MessageItem;
  symptoms?: string[];
}) {
  const isUser = message.role === "user";
  const cleaned = cleanContent(message.content);
  const isSafety = !isUser && cleaned.includes("安全警告");

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
    <div className="flex justify-start">
      <div
        className={`max-w-[85%] rounded-2xl rounded-bl-sm px-4 py-3 ${
          isSafety ? "border border-destructive/40 bg-destructive/10" : "bg-muted"
        }`}
      >
        {isSafety && (
          <div className="mb-2 flex items-center gap-1.5 text-destructive font-medium text-sm">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            安全警告
          </div>
        )}
        <div className="text-sm">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {cleaned}
          </ReactMarkdown>
        </div>
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
    </div>
  );
}
