import { ChatWindow } from "@/components/chat/ChatWindow";

/** 新对话页（threadId 为空，首条消息后由后端创建线程）。 */
export default function ChatPage() {
  return <ChatWindow threadId="" />;
}
