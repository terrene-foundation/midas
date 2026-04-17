import { Sidebar, ViewportGate } from "@/elements/Sidebar";
import { DebateOverlay } from "@/elements/DebateOverlay";

export default function ShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ViewportGate>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">{children}</main>
        <DebateOverlay />
      </div>
    </ViewportGate>
  );
}
