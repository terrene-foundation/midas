"use client";

import { useState } from "react";
import { useDeclineDecision } from "@/lib/queries/useDecisions";
import { cn } from "@/elements/ui/utils";

interface DeclineFlowProps {
  decisionId: string;
  decisionSummary?: string;
  onDeclined: () => void;
  onCancel: () => void;
  className?: string;
}

/**
 * Decline flow with confirmation step.
 * No re-auth required per spec 10 S2.2.
 */
export function DeclineFlow({
  decisionId,
  decisionSummary,
  onDeclined,
  onCancel,
  className,
}: DeclineFlowProps) {
  const [confirmed, setConfirmed] = useState(false);
  const decline = useDeclineDecision();

  const handleDecline = () => {
    decline.mutate(decisionId, {
      onSuccess: () => {
        setConfirmed(true);
        onDeclined();
      },
    });
  };

  return (
    <div className={cn("space-y-4", className)}>
      {!confirmed ? (
        <>
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-[var(--text-primary)]">
              Decline this decision?
            </h3>
            {decisionSummary && (
              <p className="text-xs text-[var(--text-secondary)]">
                {decisionSummary}
              </p>
            )}
            <p className="text-xs text-[var(--text-muted)]">
              This action will record your decline and close this decision.
            </p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={onCancel}
              className="flex-1 py-2.5 rounded-[var(--radius)] border border-[var(--border-default)] text-[var(--text-secondary)] text-sm hover:bg-[var(--bg-elevated)] transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleDecline}
              disabled={decline.isPending}
              className="flex-1 py-2.5 rounded-[var(--radius)] bg-[var(--loss-red)]/20 border border-[var(--loss-red)]/50 text-[var(--loss-red)] text-sm font-medium hover:bg-[var(--loss-red)]/30 transition-colors disabled:opacity-50"
            >
              {decline.isPending ? "Declining..." : "Confirm Decline"}
            </button>
          </div>
        </>
      ) : (
        <div className="text-center py-4">
          <div className="text-2xl mb-2">✓</div>
          <p className="text-sm text-[var(--text-secondary)]">
            Decision declined
          </p>
        </div>
      )}
    </div>
  );
}
