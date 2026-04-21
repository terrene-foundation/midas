"use client";

import Link from "next/link";
import { cn } from "@/elements/ui/utils";

type ResolutionState =
  | "decision-updated"
  | "decision-maintained"
  | "open"
  | "envelope-change";

interface ResolutionBannerProps {
  state: ResolutionState | string;
  decisionId?: string;
  onDismiss?: () => void;
}

export function ResolutionBanner({
  state,
  decisionId,
  onDismiss,
}: ResolutionBannerProps) {
  const normalizedState = state
    .toLowerCase()
    .replace(/[_-]/g, "-") as ResolutionState;

  switch (normalizedState) {
    case "decision-updated":
      return (
        <div className="flex items-center justify-between rounded bg-[var(--gain-green)]/10 border border-[var(--gain-green)]/30 p-3">
          <div className="flex items-center gap-2">
            <span className="text-[var(--gain-green)]">✓</span>
            <span className="text-sm text-[var(--text-primary)]">
              Decision updated
            </span>
          </div>
          <div className="flex items-center gap-2">
            {decisionId && (
              <Link
                href={`/decisions?id=${decisionId}`}
                className="text-xs text-[var(--accent-gold)] hover:underline"
              >
                View Decision
              </Link>
            )}
            {onDismiss && (
              <button
                onClick={onDismiss}
                className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                Dismiss
              </button>
            )}
          </div>
        </div>
      );

    case "decision-maintained":
      return (
        <div className="flex items-center justify-between rounded bg-[var(--regime-elevated)]/10 border border-[var(--regime-elevated)]/30 p-3">
          <div className="flex items-center gap-2">
            <span className="text-[var(--regime-elevated)]">↔</span>
            <span className="text-sm text-[var(--text-primary)]">
              Decision maintained — no change
            </span>
          </div>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              Dismiss
            </button>
          )}
        </div>
      );

    case "open":
      return (
        <div className="flex items-center justify-between rounded bg-[var(--bg-elevated)] border border-[var(--border-default)] p-3">
          <div className="flex items-center gap-2">
            <span className="text-[var(--text-muted)]">○</span>
            <span className="text-sm text-[var(--text-secondary)]">
              Thread open — resume anytime
            </span>
          </div>
        </div>
      );

    case "envelope-change":
      return (
        <div className="flex items-center justify-between rounded bg-[var(--accent-gold)]/10 border border-[var(--accent-gold)]/30 p-3">
          <div className="flex items-center gap-2">
            <span className="text-[var(--accent-gold)]">⚡</span>
            <span className="text-sm text-[var(--text-primary)]">
              Envelope change proposed
            </span>
          </div>
          <Link
            href="/settings?tab=envelope"
            className="text-xs text-[var(--accent-gold)] hover:underline"
          >
            Review in Settings
          </Link>
        </div>
      );

    default:
      return null;
  }
}
