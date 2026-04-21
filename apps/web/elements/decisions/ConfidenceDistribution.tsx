"use client";

import { cn } from "@/elements/ui/utils";

interface ConfidenceDistributionProps {
  confidence: number; // 0-1 scale
  className?: string;
}

/**
 * Renders confidence as a distribution visualization per spec 07 S2.7.
 * Shows a horizontal bar with gradient fill representing probability mass.
 */
export function ConfidenceDistribution({
  confidence,
  className,
}: ConfidenceDistributionProps) {
  const pct = Math.round(confidence * 100);

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex justify-between text-xs">
        <span className="text-[var(--text-muted)]">Confidence</span>
        <span className="font-mono-nums tabular-nums text-[var(--text-secondary)]">
          {pct}%
        </span>
      </div>
      <div className="h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, var(--accent-gold-dim) 0%, var(--accent-gold) 100%)`,
          }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-[var(--text-muted)]">
        <span>Low</span>
        <span>High</span>
      </div>
    </div>
  );
}
