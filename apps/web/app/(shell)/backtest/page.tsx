"use client";

import { useState } from "react";
import {
  useBacktestRuns,
  useBacktestResult,
  useBacktestRegimeBreakdown,
  useBacktestConsistency,
} from "@/lib/queries/useBacktest";
import {
  BacktestScorecard,
  EquityCurve,
  ScenarioSelector,
  RegimeBreakdown,
  SubHorizonConsistency,
  CostSensitivity,
  WhatIfPanel,
} from "@/elements/backtest";

export default function BacktestPage() {
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const { data: runsData, isPending: runsLoading } = useBacktestRuns();
  const { data: result, isPending: resultLoading } = useBacktestResult(
    selectedRun ?? "",
  );
  const { data: regimeData } = useBacktestRegimeBreakdown(selectedRun ?? "");
  const { data: consistencyData } = useBacktestConsistency(selectedRun ?? "");

  const regimePeriods =
    regimeData?.regimes?.map((r) => ({
      period: r.name,
      start_date: "",
      end_date: "",
      return: r.return_pct ? r.return_pct / 100 : null,
      sharpe: r.sharpe,
      max_drawdown: null,
      period_count: Math.round((r.time_pct ?? 0) * 100),
    })) ??
    result?.regime_breakdown?.map((r) => ({
      period: r.name,
      start_date: "",
      end_date: "",
      return: r.return_pct ? r.return_pct / 100 : null,
      sharpe: r.sharpe,
      max_drawdown: null,
      period_count: Math.round((r.time_pct ?? 0) * 100),
    })) ??
    [];

  const subHorizons =
    result?.sub_horizons ??
    (consistencyData
      ? [
          {
            label: "Monthly",
            return:
              consistencyData.monthly.positive_fraction > 0
                ? consistencyData.monthly.positive_fraction
                : null,
            periods: consistencyData.monthly.total_periods,
          },
          {
            label: "Quarterly",
            return:
              consistencyData.quarterly.positive_fraction > 0
                ? consistencyData.quarterly.positive_fraction
                : null,
            periods: consistencyData.quarterly.total_periods,
          },
        ]
      : []);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">
          Backtest
        </h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Left: scenario selector */}
        <ScenarioSelector
          runs={runsData?.runs ?? []}
          selectedRunId={selectedRun}
          onSelect={setSelectedRun}
          isPending={runsLoading}
        />

        {/* Right: scorecard + equity curve */}
        <div className="lg:col-span-3 space-y-4">
          <BacktestScorecard result={result} isPending={resultLoading} />

          {result && (
            <>
              <EquityCurve data={result.equity_curve} />

              {/* Regime breakdown + sub-horizon */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <RegimeBreakdown periods={regimePeriods} />
                <SubHorizonConsistency horizons={subHorizons} />
              </div>

              {/* Cost sensitivity + what-if */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <CostSensitivity
                  baseReturn={result.cagr}
                  costDrag={result.turnover}
                />
                <WhatIfPanel />
              </div>
            </>
          )}

          {!result && !resultLoading && (
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
