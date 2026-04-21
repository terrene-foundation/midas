"use client";

import type { BacktestRun } from "@/lib/types";
import { cn } from "@/elements/ui/utils";

interface ScenarioSelectorProps {
  runs: BacktestRun[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
  isPending?: boolean;
}

export function ScenarioSelector({
  runs,
  selectedRunId,
  onSelect,
  isPending,
}: ScenarioSelectorProps) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-3">
        Backtest Runs
      </p>
      <div className="space-y-2">
        {isPending ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-12 rounded-[var(--radius)] bg-[var(--bg-elevated)] animate-pulse"
            />
          ))
        ) : runs.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)] py-2">
            No backtest runs found
          </p>
        ) : (
          runs.map((run) => (
            <button
              key={run.id}
              onClick={() => onSelect(run.id)}
              className={cn(
                "w-full text-left rounded-[var(--radius)] border p-3 text-sm transition-colors",
                selectedRunId === run.id
                  ? "border-[var(--accent-gold)] bg-[var(--bg-hover)]"
                  : "border-[var(--border-default)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)]",
              )}
            >
              <p className="text-[var(--text-primary)] font-medium truncate">
                {run.name || `Run ${run.id.slice(0, 8)}`}
              </p>
              <div className="flex items-center justify-between mt-1">
                <span
                  className={cn(
                    "text-xs px-1.5 py-0.5 rounded",
                    run.status === "completed"
                      ? "bg-[var(--gain-green)]/10 text-[var(--gain-green)]"
                      : run.status === "failed"
                        ? "bg-[var(--loss-red)]/10 text-[var(--loss-red)]"
                        : "bg-[var(--accent-gold)]/10 text-[var(--accent-gold)]",
                  )}
                >
                  {run.status}
                </span>
                <span className="text-xs text-[var(--text-muted)]">
                  {run.completed_at
                    ? new Date(run.completed_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })
                    : run.created_at
                      ? new Date(run.created_at).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                        })
                      : ""}
                </span>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
