"use client";

import type { PulseResponse } from "@/lib/types";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { RegimeGauge } from "@/elements/regime/RegimeGauge";
import { useRegimeStore } from "@/stores/regime-store";
import { useDecisions } from "@/lib/queries/useDecisions";
import { DecisionCardSkeleton } from "@/elements/LoadingSkeleton";

interface PulseElevatedLayoutProps {
  pulse: PulseResponse | undefined;
}

export function PulseElevatedLayout({ pulse }: PulseElevatedLayoutProps) {
  const { a_t, changepointProbability } = useRegimeStore();
  const { data: decisionsData, isPending: decisionsLoading } =
    useDecisions("pending");
  const nav = pulse?.nav ?? 0;
  const changePct = pulse?.nav_change_pct ?? 0;

  return (
    <div className="p-6 space-y-4 animate-fade-in">
      <div className="space-y-2">
        <RegimeGauge
          a_t={a_t}
          transitionPressure={changepointProbability}
          size="lg"
          className="max-w-md"
        />
      </div>

      <div>
        <h2 className="text-sm font-medium text-[var(--accent-gold)] mb-2">
          Pending Decisions
        </h2>
        {decisionsLoading ? (
          <div className="space-y-2">
            <DecisionCardSkeleton />
            <DecisionCardSkeleton />
          </div>
        ) : (
          <div className="space-y-2">
            {(decisionsData?.decisions ?? []).slice(0, 3).map((d) => (
              <div
                key={d.id}
                className="rounded-[var(--radius)] border border-[var(--accent-gold)]/30 bg-[var(--bg-surface)] p-4 flex justify-between items-center"
              >
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {d.instruments || d.decision_type}
                  </p>
                  <p className="text-xs text-[var(--text-secondary)]">
                    {d.action} &middot; Confidence:{" "}
                    {(d.confidence * 100).toFixed(0)}%
                  </p>
                </div>
                <span className="text-xs text-[var(--text-muted)]">
                  {d.created_at_day}
                </span>
              </div>
            ))}
            {!decisionsData?.decisions?.length && (
              <p className="text-xs text-[var(--text-muted)]">
                No pending decisions
              </p>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-3 text-sm text-[var(--text-secondary)]">
        <span className="font-mono-nums tabular-nums">
          ${nav.toLocaleString("en-US", { minimumFractionDigits: 2 })}
        </span>
        <FinancialFigure
          value={changePct}
          format="percent"
          className="text-xs"
        />
      </div>
    </div>
  );
}
