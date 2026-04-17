"use client";

import Link from "next/link";
import { useKillSwitch } from "@/lib/queries/useCompliance";

export function KillSwitchBanner() {
  const { data: killSwitch } = useKillSwitch();

  if (!killSwitch?.isActive) return null;

  return (
    <div
      className="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-4 bg-[var(--loss-red)] px-4 py-2 animate-fade-in"
      role="alert"
    >
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
        <span className="text-sm font-bold text-white tracking-wide uppercase">
          Kill Switch Active — Trading Paused
        </span>
      </div>
      <Link
        href="/settings"
        className="rounded border border-white/50 px-3 py-0.5 text-xs font-medium text-white hover:bg-white/10 transition-colors"
      >
        View in Settings
      </Link>
    </div>
  );
}
