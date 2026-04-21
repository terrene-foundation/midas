"use client";

import { useAllocation } from "@/lib/queries/usePortfolio";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { FinancialFigure } from "@/elements/FinancialFigure";

const DRIFT_THRESHOLD = 0.02; // 2% drift threshold before highlighting

export function AllocationBars() {
  const { data, isPending } = useAllocation();

  if (isPending) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-4">
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          Allocation
        </p>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-1.5">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-6 w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (!data?.allocations?.length) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <p className="text-sm font-medium text-[var(--text-secondary)] mb-3">
          Allocation
        </p>
        <p className="text-sm text-[var(--text-muted)] text-center py-4">
          No allocation data
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-sm font-medium text-[var(--text-secondary)] mb-4">
        Allocation
      </p>
      <div className="space-y-5">
        {data.allocations.map((alloc) => {
          const isDriftOverThreshold = Math.abs(alloc.drift) > DRIFT_THRESHOLD;
          const isOverTarget = alloc.drift > 0;

          return (
            <div key={alloc.category} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--text-primary)]">
                  {alloc.category}
                </span>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono-nums tabular-nums text-[var(--text-muted)]">
                    {(alloc.target_weight * 100).toFixed(1)}% target
                  </span>
                  {isDriftOverThreshold && (
                    <FinancialFigure
                      value={alloc.drift * 100}
                      format="percent"
                      showSign
                      className="text-xs"
                    />
                  )}
                </div>
              </div>

              {/* Bar track */}
              <div className="relative h-6 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
                {/* Target marker */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-[var(--text-muted)] opacity-60"
                  style={{ left: `${alloc.target_weight * 100}%` }}
                />
                {/* Current weight fill */}
                <div
                  className={`absolute top-0 bottom-0 rounded-full transition-all ${
                    isDriftOverThreshold
                      ? isOverTarget
                        ? "bg-[var(--loss-red)]/80"
                        : "bg-[var(--accent-gold)]/80"
                      : "bg-[var(--accent-gold)]/60"
                  }`}
                  style={{ width: `${Math.min(alloc.weight * 100, 100)}%` }}
                />
              </div>

              <div className="flex items-center justify-between px-0.5">
                <span className="text-xs font-mono-nums tabular-nums text-[var(--text-secondary)]">
                  {(alloc.weight * 100).toFixed(1)}%
                </span>
                {isDriftOverThreshold && (
                  <span
                    className={`text-xs ${isOverTarget ? "text-[var(--loss-red)]" : "text-[var(--accent-gold)]"}`}
                  >
                    {isOverTarget ? "Overweight" : "Underweight"}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
