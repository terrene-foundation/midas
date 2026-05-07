import { Sidebar, ViewportGate } from "@/elements/Sidebar";
import { DebateOverlay } from "@/elements/DebateOverlay";
import { OODBanner } from "@/elements/safety/OODBanner";
import { AttentionBudgetGauge } from "@/elements/attention/AttentionBudgetGauge";
import { OnboardingGuard } from "@/elements/onboarding/OnboardingGuard";
import { NotificationCenter } from "@/elements/notifications/NotificationCenter";
import { RegimeChangeToast } from "@/elements/notifications/RegimeChangeToast";

export default function ShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ViewportGate>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <header className="flex items-center justify-between px-6 py-2 border-b border-[var(--border-default)] bg-[var(--bg-surface)]">
            <OODBanner />
            <div className="ml-4 flex items-center gap-3">
              <AttentionBudgetGauge />
              <NotificationCenter />
            </div>
          </header>
          <main className="flex-1 overflow-y-auto">
            <OnboardingGuard>{children}</OnboardingGuard>
          </main>
        </div>
        <DebateOverlay />
      </div>
      <RegimeChangeToast />
    </ViewportGate>
  );
}
