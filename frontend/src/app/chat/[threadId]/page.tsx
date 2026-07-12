import { ChatWindow } from "@/components/chat/ChatWindow";

/** 指定会话页（Next.js 16: params 为 Promise，需 await）。 */
export default async function ThreadPage({
  params,
}: {
  params: Promise<{ threadId: string }>;
}) {
  const { threadId } = await params;
  return <ChatWindow threadId={threadId} />;
}
