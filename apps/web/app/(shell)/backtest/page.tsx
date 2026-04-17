"use client";

import { useState } from "react";
import { useBacktestRuns, useBacktestResult } from "@/lib/queries/useBacktest";
import {
  BacktestScorecardSkeleton,
  Skeleton,
} from "@/elements/LoadingSkeleton";

export default function BacktestPage() {
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const { data: runsData, isPending: runsLoading } = useBacktestRuns();
  const { data: result, isPending: resultLoading } = useBacktestResult(
    selectedRun ?? "",
  );

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">
        Backtest
      </h1>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="space-y-2">
          <h2 className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
            Runs
          </h2>
          {runsLoading ? (
            <Skeleton variant="card" />
          ) : (
            (runsData?.runs ?? []).map((r) => (
              <button
                key={r.id}
                onClick={() => setSelectedRun(r.id)}
                className={`w-full text-left rounded-[var(--radius)] border p-3 text-sm transition-colors ${
                  selectedRun === r.id
                    ? "border-[var(--accent-gold)] bg-[var(--bg-hover)]"
                    : "border-[var(--border-default)] bg-[var(--bg-surface)]"
                }`}
              >
                <p className="text-[var(--text-primary)]">
                  {r.name || `Run ${r.id.slice(0, 8)}`}
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  {r.status}
                </p>
              </button>
            ))
          )}
        </div>

        <div className="lg:col-span-3">
          {resultLoading ? (
            <BacktestScorecardSkeleton />
          ) : result ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                <MetricTile label="CAGR" value={result.cagr} fmt="percent" />
                <MetricTile label="Sharpe" value={result.sharpe} fmt="number" />
                <MetricTile
                  label="Max Drawdown"
                  value={result.max_drawdown}
                  fmt="percent"
                />
                <MetricTile label="Calmar" value={result.calmar} fmt="number" />
                <MetricTile
                  label="Turnover"
                  value={result.turnover}
                  fmt="percent"
                />
                <MetricTile
                  label="Win Rate"
                  value={result.win_rate}
                  fmt="percent"
                />
              </div>

              {result.equity_curve && result.equity_curve.length > 0 && (
                <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
                  <h3 className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-3">
                    Equity Curve
                  </h3>
                  <div className="h-48 flex items-end gap-px">
                    {(() => {
                      const maxVal = Math.max(
                        ...result.equity_curve.map((p) => p.value),
                      );
                      return result.equity_curve.map((point, i) => (
                        <div
                          key={i}
                          className="flex-1 bg-[var(--accent-gold)]/60 rounded-t-sm min-w-[1px]"
                          style={{
                            height: `${Math.max(1, maxVal > 0 ? (point.value / maxVal) * 100 : 0)}%`,
                          }}
                          title={`${point.date}: ${point.value.toFixed(2)}`}
                        />
                      ));
                    })()}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-8 text-center">
              <p className="text-sm text-[var(--text-muted)]">
                Select a backtest run to view results
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricTile({
  label,
  value,
  fmt,
}: {
  label: string;
  value: number | null;
  fmt: "percent" | "number";
}) {
  const display =
    value == null
      ? "--"
      : fmt === "percent"
        ? `${(value * 100).toFixed(2)}%`
        : value.toFixed(3);
  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3">
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className="text-lg font-semibold font-mono-nums tabular-nums text-[var(--text-primary)] mt-1">
        {display}
      </p>
    </div>
  );
}
