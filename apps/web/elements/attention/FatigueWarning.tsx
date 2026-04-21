"use client";

import { useAttentionStore } from "@/stores/attention-store";

export function FatigueWarning({ className }: { className?: string }) {
  const fatigueSignal = useAttentionStore((s) => s.fatigueSignal);

  if (!fatigueSignal) return null;

  return (
    <div
      className={`rounded-[var(--radius)] border border-[var(--accent-gold)]/40 bg-[var(--accent-gold)]/10 px-4 py-3 ${className ?? ""}`}
      role="alert"
    >
      <p className="text-sm text-[var(--accent-gold)]">
        <span className="font-semibold">
          You are approving without reading the full brief.{" "}
        </span>
        <span className="text-[var(--text-secondary)]">
          Consider taking a break. Rapid approvals without deliberation reduce
          the quality of oversight.
        </span>
      </p>
    </div>
  );
}
