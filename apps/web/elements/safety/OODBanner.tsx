"use client";

import { useRegimeStore } from "@/stores/regime-store";

const OOD_THRESHOLD = 0.7;

interface OODBannerProps {
  className?: string;
}

export function OODBanner({ className }: OODBannerProps) {
  const oodScore = useRegimeStore((s) => s.oodScore);

  if (oodScore <= OOD_THRESHOLD) return null;

  return (
    <div
      className={`rounded-[var(--radius)] border border-[var(--regime-crisis)] bg-[var(--regime-crisis)]/10 px-4 py-3 ${className ?? ""}`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 w-2 h-2 rounded-full bg-[var(--regime-crisis)] flex-shrink-0" />
        <div className="space-y-1">
          <p className="text-sm font-semibold text-[var(--regime-crisis)]">
            I am less calibrated in this state
          </p>
          <p className="text-xs text-[var(--text-secondary)]">
            My out-of-distribution score is elevated, meaning recent market
            conditions fall outside my training distribution. Decision
            confidence may be overstated. Take extra care when reviewing
            recommendations.
          </p>
        </div>
      </div>
    </div>
  );
}
