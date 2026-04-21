"use client";

import { useState } from "react";
import { useBatchReview } from "@/lib/queries/useDecisions";
import type { DecisionSummary } from "@/lib/types";
import { cn } from "@/elements/ui/utils";

interface BatchReviewPanelProps {
  decisions: DecisionSummary[];
  fatigueReason?: string;
  onComplete: () => void;
  onCancel: () => void;
  className?: string;
}

/**
 * Batch review mode for digest approvals when attention fatigue detected.
 * Allows user to quickly review multiple decisions in bulk.
 */
export function BatchReviewPanel({
  decisions,
  fatigueReason,
  onComplete,
  onCancel,
  className,
}: BatchReviewPanelProps) {
  const [selections, setSelections] = useState<
    Record<string, "approve" | "decline">
  >(() =>
    decisions.reduce((acc, d) => ({ ...acc, [d.id]: "approve" as const }), {}),
  );

  const batchReview = useBatchReview();

  const toggleDecision = (id: string) => {
    setSelections((prev) => ({
      ...prev,
      [id]: prev[id] === "approve" ? "decline" : "approve",
    }));
  };

  const handleSubmit = () => {
    const actions = Object.entries(selections).map(([decision_id, action]) => ({
      decision_id,
      action,
    }));
    batchReview.mutate(actions, {
      onSuccess: () => {
        onComplete();
      },
    });
  };

  const approvedCount = Object.values(selections).filter(
    (v) => v === "approve",
  ).length;
  const declinedCount = Object.values(selections).filter(
    (v) => v === "decline",
  ).length;

  return (
    <div
      className={cn(
        "rounded-[var(--radius)] border border-[var(--accent-gold)]/50 bg-[var(--bg-surface)] p-4 space-y-4",
        className,
      )}
    >
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-[var(--accent-gold)]">⚡</span>
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Batch Review Mode
          </h3>
        </div>
        {fatigueReason && (
          <p className="text-xs text-[var(--text-muted)]">{fatigueReason}</p>
        )}
        <p className="text-xs text-[var(--text-secondary)]">
          {decisions.length} decisions pending. Review all at once for
          efficiency.
        </p>
      </div>

      {/* Decision list */}
      <div className="space-y-2 max-h-[300px] overflow-y-auto">
        {decisions.map((d) => {
          const selection = selections[d.id];
          return (
            <div
              key={d.id}
              onClick={() => toggleDecision(d.id)}
              className={cn(
                "flex items-center justify-between p-3 rounded-[var(--radius)] border cursor-pointer transition-colors",
                selection === "approve"
                  ? "border-[var(--gain-green)]/50 bg-[var(--gain-green)]/5"
                  : selection === "decline"
                    ? "border-[var(--loss-red)]/50 bg-[var(--loss-red)]/5"
                    : "border-[var(--border-default)] bg-[var(--bg-elevated)]",
              )}
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-[var(--text-primary)] truncate">
                  {d.instruments || d.decision_type}
                </p>
                <p className="text-xs text-[var(--text-muted)] truncate">
                  {d.action}
                </p>
              </div>
              <div className="flex items-center gap-2 ml-3">
                <span
                  className={cn(
                    "text-xs font-medium px-2 py-1 rounded-full",
                    selection === "approve"
                      ? "bg-[var(--gain-green)]/20 text-[var(--gain-green)]"
                      : "bg-[var(--loss-red)]/20 text-[var(--loss-red)]",
                  )}
                >
                  {selection === "approve" ? "Approve" : "Decline"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex gap-4">
          <span className="text-[var(--gain-green)]">
            Approve: {approvedCount}
          </span>
          <span className="text-[var(--loss-red)]">
            Decline: {declinedCount}
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <button
          onClick={onCancel}
          className="flex-1 py-2 rounded-[var(--radius)] border border-[var(--border-default)] text-[var(--text-secondary)] text-sm hover:bg-[var(--bg-elevated)] transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={batchReview.isPending}
          className="flex-1 py-2 rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-base)] text-sm font-medium hover:brightness-110 transition-all disabled:opacity-50"
        >
          {batchReview.isPending
            ? "Submitting..."
            : `Submit ${decisions.length} Decisions`}
        </button>
      </div>
    </div>
  );
}
