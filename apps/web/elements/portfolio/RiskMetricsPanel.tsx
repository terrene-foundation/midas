"use client";

import { useRiskMetrics } from "@/lib/queries/usePortfolio";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { TrendingDown, Activity, BarChart3, Target, Zap } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: number | null;
  format?: "percent" | "number" | "currency";
  icon: React.ReactNode;
  description?: string;
}

export function RiskMetricsPanel() {
  const { data, isPending } = useRiskMetrics();

  if (isPending) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <p className="text-sm font-medium text-[var(--text-secondary)] mb-4">
          Risk Metrics
        </p>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="space-y-2 p-3 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)]"
            >
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-6 w-20" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Available metrics from API; some spec-required metrics (Sortino, TrackingError, IR, Alpha, M², Treynor)
  // require future API expansion. Using null coalescing for safety.
  const metrics: MetricCardProps[] = [
    {
      label: "Volatility",
      value: data?.volatility ?? null,
      format: "percent",
      icon: <Activity size={14} />,
      description: "Annualized portfolio volatility",
    },
    {
      label: "Sharpe Ratio",
      value: data?.sharpe_ratio ?? null,
      format: "number",
      icon: <Target size={14} />,
      description: "Risk-adjusted return",
    },
    {
      label: "Max Drawdown",
      value: data?.max_drawdown ?? null,
      format: "percent",
      icon: <TrendingDown size={14} />,
      description: "Largest peak-to-trough",
    },
    {
      label: "VaR (95%)",
      value: data?.portfolio_var_95 ?? null,
      format: "percent",
      icon: <BarChart3 size={14} />,
      description: "Value at Risk, 1-day 95%",
    },
    {
      label: "VaR (99%)",
      value: data?.portfolio_var_99 ?? null,
      format: "percent",
      icon: <Zap size={14} />,
      description: "Value at Risk, 1-day 99%",
    },
  ];

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-sm font-medium text-[var(--text-secondary)] mb-4">
        Risk Metrics
      </p>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {metrics.map((m) => (
          <RiskMetricCard key={m.label} {...m} />
        ))}
      </div>
    </div>
  );
}

function RiskMetricCard({
  label,
  value,
  format = "number",
  icon,
  description,
}: MetricCardProps) {
  const display =
    value == null
      ? "--"
      : format === "percent"
        ? `${(value * 100).toFixed(2)}%`
        : format === "currency"
          ? `$${value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`
          : value.toFixed(3);

  return (
    <div
      className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 space-y-1"
      title={description}
    >
      <div className="flex items-center gap-1.5 text-[var(--text-muted)]">
        {icon}
        <p className="text-xs uppercase tracking-wider">{label}</p>
      </div>
      <p className="text-lg font-semibold font-mono-nums tabular-nums text-[var(--text-primary)]">
        {display}
      </p>
    </div>
  );
}
