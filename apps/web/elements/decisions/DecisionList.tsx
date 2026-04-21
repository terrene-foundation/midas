"use client";

import { useDecisions, useBrief } from "@/lib/queries/useDecisions";
import type { BriefResponse } from "@/lib/types";
import { DecisionCard } from "./DecisionCard";
import { DecisionCardSkeleton } from "@/elements/LoadingSkeleton";
import { BatchReviewPanel } from "./BatchReviewPanel";
import { useRegimeStore } from "@/stores/regime-store";
import { useAttentionStore } from "@/stores/attention-store";
import { cn } from "@/elements/ui/utils";

interface DecisionListProps {
  status?: string;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  className?: string;
}

export function DecisionList({
  status = "pending",
  selectedId,
  onSelect,
  className,
}: DecisionListProps) {
  const { data, isPending } = useDecisions(status);
  const { a_t, oodScore } = useRegimeStore();
  const { fatigueSignal } = useAttentionStore();

  // Fetch brief for selected decision
  const { data: selectedBrief } = useBrief(selectedId ?? "") as {
    data: BriefResponse | undefined;
  };

  if (isPending) {
    return (
      <div className={cn("space-y-3", className)}>
        <DecisionCardSkeleton />
        <DecisionCardSkeleton />
        <DecisionCardSkeleton />
      </div>
    );
  }

  const decisions = data?.decisions ?? [];

  if (decisions.length === 0) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-8 text-center">
        <p className="text-sm text-[var(--text-muted)]">
          No {status} decisions
        </p>
      </div>
    );
  }

  // If fatigue detected, show batch review panel instead
  if (fatigueSignal && status === "pending" && decisions.length > 3) {
    return (
      <BatchReviewPanel
        decisions={decisions}
        fatigueReason="Attention fatigue detected. Batch review mode enabled for efficiency."
        onComplete={() => {}}
        onCancel={() => {}}
      />
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      {decisions.map((decision) => (
        <DecisionCard
          key={decision.id}
          decision={decision}
          brief={selectedId === decision.id ? selectedBrief : undefined}
          band={useRegimeStore.getState().band}
          isSelected={selectedId === decision.id}
          onSelect={() => onSelect?.(decision.id)}
          a_t={a_t}
          oodScore={oodScore}
        />
      ))}
    </div>
  );
}
