"use client";

import type { BacktestResult } from "@/lib/types";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { BacktestScorecardSkeleton } from "@/elements/LoadingSkeleton";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Target,
  BarChart3,
  RefreshCw,
  Percent,
  Award,
} from "lucide-react";

interface BacktestScorecardProps {
  result: BacktestResult | null | undefined;
  isPending?: boolean;
}

interface ScoreRow {
  label: string;
  value: number | null;
  format: "percent" | "number";
  icon: React.ReactNode;
  invertColor?: boolean; // for max drawdown — lower is better
}

export function BacktestScorecard({
  result,
  isPending,
}: BacktestScorecardProps) {
  if (isPending) return <BacktestScorecardSkeleton />;

  if (!result) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 text-center">
        <p className="text-sm text-[var(--text-muted)]">
          No backtest results available
        </p>
      </div>
    );
  }

  const rows: ScoreRow[] = [
    {
      label: "CAGR",
      value: result.cagr,
      format: "percent",
      icon: <TrendingUp size={14} />,
    },
    {
      label: "Sharpe",
      value: result.sharpe,
      format: "number",
      icon: <Target size={14} />,
    },
    {
      label: "Max Drawdown",
      value: result.max_drawdown,
      format: "percent",
      icon: <TrendingDown size={14} />,
      invertColor: true,
    },
    {
      label: "Calmar",
      value: result.calmar,
      format: "number",
      icon: <Activity size={14} />,
    },
    {
      label: "Turnover",
      value: result.turnover,
      format: "percent",
      icon: <RefreshCw size={14} />,
    },
    {
      label: "Win Rate",
      value: result.win_rate,
      format: "percent",
      icon: <Award size={14} />,
    },
  ];

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          Scorecard
        </p>
        <p className="text-xs text-[var(--text-muted)]">
          Run {result.run_id?.slice(0, 8)}
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {rows.map((row) => (
          <ScoreCell key={row.label} {...row} />
        ))}
      </div>
    </div>
  );
}

function ScoreCell({ label, value, format, icon, invertColor }: ScoreRow) {
  const isPositive = value != null && value > 0;
  const isNegative = value != null && value < 0;

  // For most metrics, positive is good. For max drawdown, negative is normal (it's a loss).
  // invertColor: the display is inverted (lower absolute value = better)
  const showColor = invertColor ? isNegative : isPositive;
  const lossColor = isNegative && !invertColor;

  const display =
    value == null
      ? "--"
      : format === "percent"
        ? `${(value * 100).toFixed(2)}%`
        : value.toFixed(3);

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 space-y-1">
      <div className="flex items-center gap-1.5 text-[var(--text-muted)]">
        {icon}
        <p className="text-xs uppercase tracking-wider">{label}</p>
      </div>
      <p
        className={`text-xl font-semibold font-mono-nums tabular-nums ${
          value == null
            ? "text-[var(--text-muted)]"
            : showColor
              ? "text-[var(--gain-green)]"
              : lossColor
                ? "text-[var(--loss-red)]"
                : "text-[var(--text-primary)]"
        }`}
      >
        {display}
      </p>
    </div>
  );
}
