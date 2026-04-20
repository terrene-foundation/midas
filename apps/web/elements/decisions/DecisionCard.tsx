"use client";

import { useState } from "react";
import type { DecisionSummary, BriefResponse } from "@/lib/types";
import { ConfidenceDistribution } from "./ConfidenceDistribution";
import { ApprovalFlow } from "./ApprovalFlow";
import { DeclineFlow } from "./DeclineFlow";
import { BriefRenderer } from "./BriefRenderer";
import type { Band } from "@/stores/regime-store";
import { useDebateOverlayStore } from "@/stores/debate-overlay-store";
import { cn } from "@/elements/ui/utils";

interface DecisionCardProps {
  decision: DecisionSummary;
  brief?: BriefResponse;
  band: Band;
  isSelected?: boolean;
  onSelect?: () => void;
  a_t: number;
  oodScore?: number;
  currentPrice?: number;
  briefPrice?: number;
  className?: string;
}

interface DecisionWindowProgressProps {
  createdAt: string;
  expiresAt?: string;
  className?: string;
}

/**
 * Decision window progress bar (NOT countdown timer) per spec 10 S6.1
 */
function DecisionWindowProgress({
  createdAt,
  expiresAt,
  className,
}: DecisionWindowProgressProps) {
  const created = new Date(createdAt).getTime();
  const now = Date.now();
  const windowDuration = 24 * 60 * 60 * 1000; // 24 hour window
  const expires = expiresAt
    ? new Date(expiresAt).getTime()
    : created + windowDuration;

  const elapsed = now - created;
  const remaining = expires - now;
  const progress = Math.max(0, Math.min(1, remaining / windowDuration));
  const progressPct = Math.round(progress * 100);

  const urgencyColor =
    progress > 0.5
      ? "bg-[var(--gain-green)]"
      : progress > 0.25
        ? "bg-[var(--accent-gold)]"
        : "bg-[var(--loss-red)]";

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex justify-between text-[10px]">
        <span className="text-[var(--text-muted)]">Decision window</span>
        <span
          className={cn(
            "font-mono-nums",
            progress < 0.25
              ? "text-[var(--loss-red)]"
              : "text-[var(--text-secondary)]",
          )}
        >
          {progressPct}% remaining
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-300",
            urgencyColor,
          )}
          style={{ width: `${progressPct}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Top-of-fold card showing decision details and action buttons.
 * Approve and Decline buttons are NOT adjacent per spec 10 S2.2
 */
export function DecisionCard({
  decision,
  brief,
  band,
  isSelected,
  onSelect,
  a_t,
  oodScore,
  currentPrice,
  briefPrice,
  className,
}: DecisionCardProps) {
  const [showDecline, setShowDecline] = useState(false);
  const openDebate = useDebateOverlayStore((s) => s.openDebate);

  const isUrgentOrCrisis = a_t >= 0.5;

  // Dollar impact comes from brief when expanded, or estimated from decision confidence
  // and portfolio size. Brief provides the authoritative figure.
  const dollarImpact = brief?.dollar_impact ?? decision.dollar_impact ?? 0;

  return (
    <div
      className={cn(
        "rounded-[var(--radius)] border bg-[var(--bg-surface)] transition-all",
        isSelected
          ? "border-[var(--accent-gold)] shadow-lg"
          : "border-[var(--border-default)] hover:border-[var(--border-accent)]",
        className,
      )}
    >
      {/* Card Header - Clickable to select */}
      <button onClick={onSelect} className="w-full text-left p-4 space-y-3">
        {/* Top row: Type and confidence */}
        <div className="flex justify-between items-start">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-xs px-2 py-0.5 rounded bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
                {decision.decision_type}
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {decision.instruments}
              </span>
            </div>
          </div>
          <ConfidenceDistribution
            confidence={decision.confidence}
            className="w-[120px]"
          />
        </div>

        {/* Action summary */}
        <p className="text-sm text-[var(--text-primary)] font-medium">
          {decision.action}
        </p>

        {/* Dollar impact and window */}
        <div className="flex justify-between items-end">
          <div className="space-y-1">
            <p className="text-[10px] text-[var(--text-muted)]">
              Dollar impact
            </p>
            <p className="text-sm font-mono-nums tabular-nums text-[var(--text-secondary)]">
              ${dollarImpact.toLocaleString()}
            </p>
          </div>
          <DecisionWindowProgress createdAt={decision.created_at_day} />
        </div>
      </button>

      {/* Expanded brief view */}
      {isSelected && brief && (
        <div className="px-4 pb-4 space-y-4">
          <div className="border-t border-[var(--border-default)] pt-4">
            <BriefRenderer
              brief={brief}
              a_t={a_t}
              band={band}
              dollarImpact={dollarImpact}
              confidence={decision.confidence}
              oodScore={oodScore}
            />
          </div>

          {/* Action buttons - SPATIAL SEPARATION per 10 S2.2 */}
          {!showDecline ? (
            <div className="space-y-3">
              {/* Primary: Approve - full width, separated */}
              <ApprovalFlow
                decisionId={decision.id}
                band={band}
                isUrgentOrCrisis={isUrgentOrCrisis}
                needsReAuth={isUrgentOrCrisis}
                currentPrice={currentPrice}
                briefPrice={briefPrice}
                onApproved={() => {}}
                onCancel={() => {}}
              />

              {/* Secondary actions: separated vertically */}
              <div className="flex justify-between">
                <button
                  onClick={() =>
                    openDebate({
                      id: decision.id,
                      type: decision.decision_type,
                    })
                  }
                  className="px-4 py-2 rounded-[var(--radius)] border border-[var(--border-default)] text-[var(--text-secondary)] text-sm hover:bg-[var(--bg-elevated)] transition-colors"
                >
                  Debate
                </button>
                <button
                  onClick={() => setShowDecline(true)}
                  className="px-4 py-2 rounded-[var(--radius)] border border-[var(--loss-red)]/30 text-[var(--loss-red)]/70 text-sm hover:bg-[var(--loss-red)]/10 transition-colors"
                >
                  Decline
                </button>
              </div>
            </div>
          ) : (
            <DeclineFlow
              decisionId={decision.id}
              decisionSummary={decision.action}
              onDeclined={() => {}}
              onCancel={() => setShowDecline(false)}
            />
          )}
        </div>
      )}
    </div>
  );
}
