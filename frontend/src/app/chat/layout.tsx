import { AppShell } from "@/components/layout/AppShell";

/** /chat 路由组共享布局：应用外壳（侧边栏 + 守卫）。 */
export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
