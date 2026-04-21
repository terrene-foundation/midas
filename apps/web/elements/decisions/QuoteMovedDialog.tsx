"use client";

import { useState } from "react";
import { cn } from "@/elements/ui/utils";

interface QuoteMovedDialogProps {
  open: boolean;
  priceChangePct: number;
  band: "calm" | "elevated" | "urgent" | "crisis";
  onProceedAtCurrent: () => void;
  onSetLimit: () => void;
  onCancel: () => void;
  className?: string;
}

/**
 * Dialog shown when price has moved since brief was generated.
 * Per spec 10 S6.4 - thresholds: Calm 0.5%, Elevated 0.3%, Urgent 0.2%, Crisis 0.1%
 */
export function QuoteMovedDialog({
  open,
  priceChangePct,
  band,
  onProceedAtCurrent,
  onSetLimit,
  onCancel,
  className,
}: QuoteMovedDialogProps) {
  const [selected, setSelected] = useState<"current" | "limit" | null>(null);

  if (!open) return null;

  const absChange = Math.abs(priceChangePct);
  const isPositive = priceChangePct > 0;
  const colorClass = isPositive
    ? "text-[var(--gain-green)]"
    : "text-[var(--loss-red)]";

  const thresholds = {
    calm: 0.5,
    elevated: 0.3,
    urgent: 0.2,
    crisis: 0.1,
  };

  const threshold = thresholds[band];
  const breached = absChange >= threshold;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />
      <div
        className={cn(
          "relative w-full max-w-sm rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4 animate-fade-in",
          className,
        )}
      >
        <div className="text-center space-y-2">
          <div
            className={cn(
              "text-3xl font-mono-nums tabular-nums font-semibold",
              colorClass,
            )}
          >
            {isPositive ? "+" : ""}
            {priceChangePct.toFixed(2)}%
          </div>
          <p className="text-sm text-[var(--text-secondary)]">
            Price moved since brief was generated
          </p>
          {breached && (
            <div className="inline-block px-2 py-1 rounded text-xs bg-[var(--loss-red)]/10 text-[var(--loss-red)] border border-[var(--loss-red)]/30">
              Threshold breached for {band} regime ({threshold}% max)
            </div>
          )}
        </div>

        <div className="space-y-2">
          <button
            onClick={() => {
              setSelected("current");
              onProceedAtCurrent();
            }}
            className={cn(
              "w-full p-3 rounded-[var(--radius)] border text-left transition-colors",
              selected === "current"
                ? "border-[var(--accent-gold)] bg-[var(--accent-gold)]/10"
                : "border-[var(--border-default)] bg-[var(--bg-elevated)] hover:border-[var(--border-accent)]",
            )}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  Proceed at current price
                </p>
                <p className="text-xs text-[var(--text-muted)]">
                  Accept the new price and continue
                </p>
              </div>
              <span className="text-[var(--text-muted)]">→</span>
            </div>
          </button>

          <button
            onClick={() => {
              setSelected("limit");
              onSetLimit();
            }}
            className={cn(
              "w-full p-3 rounded-[var(--radius)] border text-left transition-colors",
              selected === "limit"
                ? "border-[var(--accent-gold)] bg-[var(--accent-gold)]/10"
                : "border-[var(--border-default)] bg-[var(--bg-elevated)] hover:border-[var(--border-accent)]",
            )}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  Set a limit
                </p>
                <p className="text-xs text-[var(--text-muted)]">
                  Cancel if price moves further
                </p>
              </div>
              <span className="text-[var(--text-muted)]">→</span>
            </div>
          </button>

          <button
            onClick={onCancel}
            className="w-full p-3 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] text-center text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
