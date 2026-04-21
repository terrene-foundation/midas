"use client";

import { cn } from "@/elements/ui/utils";

interface HonestyBannerProps {
  oodScore: number; // 0-1, out-of-distribution score
  className?: string;
}

/**
 * Displays honesty warning for OOD conditions per spec 10 S8.1.
 * Shows when model confidence may be unreliable.
 */
export function HonestyBanner({ oodScore, className }: HonestyBannerProps) {
  if (oodScore < 0.3) return null;

  const severity =
    oodScore >= 0.7 ? "high" : oodScore >= 0.5 ? "medium" : "low";

  return (
    <div
      className={cn(
        "rounded-[var(--radius)] border p-3 text-sm",
        severity === "high" &&
          "border-[var(--loss-red)]/50 bg-[var(--loss-red)]/10",
        severity === "medium" &&
          "border-[var(--regime-urgent)]/50 bg-[var(--regime-urgent)]/10",
        severity === "low" &&
          "border-[var(--accent-gold)]/50 bg-[var(--accent-gold)]/10",
        className,
      )}
    >
      <div className="flex items-start gap-2">
        <span
          className={cn(
            "text-base",
            severity === "high" && "text-[var(--loss-red)]",
            severity === "medium" && "text-[var(--regime-urgent)]",
            severity === "low" && "text-[var(--accent-gold)]",
          )}
        >
          ⚠
        </span>
        <div className="space-y-1">
          <p className="font-medium text-[var(--text-primary)]">
            Reduced calibration in this state
          </p>
          <p className="text-xs text-[var(--text-secondary)]">
            I am less confident in my probabilistic estimates when market
            conditions are this unusual. Consider requiring human review before
            acting on this decision.
          </p>
        </div>
      </div>
    </div>
  );
}
