"use client";

import type { Signal } from "@/lib/types";
import { cn } from "@/elements/ui/utils";

interface SignalCardProps {
  signal: Signal;
  onClick?: () => void;
  className?: string;
}

function getImpactLevel(strength: number): "high" | "medium" | "low" | "none" {
  if (strength >= 0.7) return "high";
  if (strength >= 0.4) return "medium";
  if (strength >= 0.2) return "low";
  return "none";
}

function ImpactBadge({ level }: { level: "high" | "medium" | "low" | "none" }) {
  const config = {
    high: {
      label: "High",
      class:
        "bg-[var(--loss-red)]/20 text-[var(--loss-red)] border-[var(--loss-red)]/30",
    },
    medium: {
      label: "Medium",
      class:
        "bg-[var(--accent-gold)]/20 text-[var(--accent-gold)] border-[var(--accent-gold)]/30",
    },
    low: {
      label: "Low",
      class:
        "bg-[var(--gain-green)]/20 text-[var(--gain-green)] border-[var(--gain-green)]/30",
    },
    none: {
      label: "None",
      class:
        "bg-[var(--bg-elevated)] text-[var(--text-muted)] border-[var(--border-default)]",
    },
  };

  const { label, class: className } = config[level];

  return (
    <span
      className={cn(
        "text-[10px] font-medium px-2 py-0.5 rounded-full border",
        className,
      )}
    >
      {label}
    </span>
  );
}

/**
 * Signal card showing headline, ticker, sentiment, portfolio impact, and timestamp.
 */
export function SignalCard({ signal, onClick, className }: SignalCardProps) {
  const impactLevel = getImpactLevel(signal.strength);

  const sentimentColor =
    signal.direction === "bullish"
      ? "bg-[var(--gain-green)]"
      : signal.direction === "bearish"
        ? "bg-[var(--loss-red)]"
        : "bg-[var(--accent-gold)]";

  const directionLabel =
    signal.direction === "bullish"
      ? "Bullish"
      : signal.direction === "bearish"
        ? "Bearish"
        : "Neutral";

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 hover:border-[var(--border-accent)] transition-colors",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {/* Headline */}
          <div className="flex items-center gap-2 mb-1">
            <span className={cn("w-2 h-2 rounded-full", sentimentColor)} />
            <p className="text-sm text-[var(--text-primary)] font-medium truncate">
              {signal.instrument}
            </p>
            <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] text-[var(--text-muted)]">
              {signal.signal_type}
            </span>
          </div>

          {/* Details */}
          <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
            <span>{signal.source}</span>
            <span className="text-[var(--text-muted)]">·</span>
            <span>{directionLabel}</span>
            <span className="text-[var(--text-muted)]">·</span>
            <span className="font-mono-nums">
              {(signal.strength * 100).toFixed(0)}% strength
            </span>
          </div>
        </div>

        {/* Right side: Impact badge and timestamp */}
        <div className="flex flex-col items-end gap-2">
          <ImpactBadge level={impactLevel} />
          <span className="text-[10px] text-[var(--text-muted)] whitespace-nowrap">
            {new Date(signal.timestamp).toLocaleDateString()}
          </span>
        </div>
      </div>
    </button>
  );
}
