"use client";

import type { Signal } from "@/lib/types";
import { useDecisions } from "@/lib/queries/useDecisions";
import { useDebateOverlayStore } from "@/stores/debate-overlay-store";
import { cn } from "@/elements/ui/utils";

interface SignalDetailSheetProps {
  signal: Signal | null;
  onClose: () => void;
}

/**
 * Detail sheet for drilling into how a signal affects pending decisions.
 * Links to Debate thread for the relevant decision.
 */
export function SignalDetailSheet({ signal, onClose }: SignalDetailSheetProps) {
  const openDebate = useDebateOverlayStore((s) => s.openDebate);
  const { data: decisionsData } = useDecisions("pending");

  if (!signal) return null;

  // Find related decisions (in a real app, this would be filtered by signal.instrument)
  const relatedDecisions = (decisionsData?.decisions ?? []).filter((d) =>
    d.instruments?.toLowerCase().includes(signal.instrument.toLowerCase()),
  );

  const sentimentColor =
    signal.direction === "bullish"
      ? "text-[var(--gain-green)]"
      : signal.direction === "bearish"
        ? "text-[var(--loss-red)]"
        : "text-[var(--accent-gold)]";

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-lg h-full bg-[var(--bg-surface)] border-l border-[var(--border-default)] flex flex-col animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-default)]">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Signal Details
            </h2>
            <p className="text-xs text-[var(--text-muted)]">
              {signal.instrument} · {signal.signal_type}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Close detail panel"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {/* Signal summary */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--text-muted)]">
                Direction
              </span>
              <span className={cn("text-sm font-medium", sentimentColor)}>
                {signal.direction.charAt(0).toUpperCase() +
                  signal.direction.slice(1)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--text-muted)]">Source</span>
              <span className="text-sm text-[var(--text-primary)]">
                {signal.source}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--text-muted)]">Strength</span>
              <span className="text-sm font-mono-nums text-[var(--text-primary)]">
                {(signal.strength * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--text-muted)]">
                Published
              </span>
              <span className="text-sm text-[var(--text-secondary)]">
                {new Date(signal.timestamp).toLocaleString()}
              </span>
            </div>
          </div>

          {/* Related decisions */}
          {relatedDecisions.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-medium text-[var(--accent-gold)] uppercase tracking-wider">
                Affects Pending Decisions
              </h3>
              <div className="space-y-2">
                {relatedDecisions.map((d) => (
                  <div
                    key={d.id}
                    className="p-3 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)]"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-[var(--text-primary)]">
                          {d.decision_type}
                        </p>
                        <p className="text-xs text-[var(--text-muted)]">
                          {d.action}
                        </p>
                      </div>
                      <button
                        onClick={() =>
                          openDebate({
                            id: d.id,
                            type: d.decision_type,
                          })
                        }
                        className="px-3 py-1.5 rounded-[var(--radius)] border border-[var(--accent-gold)]/30 text-[var(--accent-gold)] text-xs hover:bg-[var(--accent-gold)]/10 transition-colors"
                      >
                        Debate
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {relatedDecisions.length === 0 && (
            <div className="text-center py-8">
              <p className="text-sm text-[var(--text-muted)]">
                No pending decisions affected by this signal
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
