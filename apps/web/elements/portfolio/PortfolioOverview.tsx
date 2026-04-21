"use client";

import { usePortfolio, useAttribution } from "@/lib/queries/usePortfolio";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  Banknote,
  BarChart3,
} from "lucide-react";

export function PortfolioOverview() {
  const { data: portfolio, isPending } = usePortfolio();
  const { data: attribution } = useAttribution();

  if (isPending) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <div className="space-y-1">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-11 w-56" />
            <Skeleton className="h-4 w-32 mt-2" />
          </div>
          <div className="flex gap-4">
            <Skeleton className="h-16 w-32" variant="rect" />
            <Skeleton className="h-16 w-32" variant="rect" />
            <Skeleton className="h-16 w-32" variant="rect" />
          </div>
        </div>
      </div>
    );
  }

  const totalReturn = attribution?.total_return ?? 0;

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
        {/* NAV Hero */}
        <div className="space-y-1">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1.5">
            <Wallet size={12} />
            Net Asset Value
          </p>
          <p className="text-4xl font-semibold font-mono-nums tabular-nums text-[var(--text-primary)]">
            $
            {(portfolio?.nav ?? 0).toLocaleString("en-US", {
              minimumFractionDigits: 2,
            })}
          </p>
          <div className="flex items-center gap-2 mt-1">
            {totalReturn !== 0 ? (
              <span
                className={cn(
                  "flex items-center gap-1 text-sm",
                  totalReturn >= 0
                    ? "text-[var(--gain-green)]"
                    : "text-[var(--loss-red)]",
                )}
              >
                {totalReturn >= 0 ? (
                  <TrendingUp size={14} />
                ) : (
                  <TrendingDown size={14} />
                )}
                <FinancialFigure
                  value={totalReturn * 100}
                  format="percent"
                  showSign
                />
                <span className="text-[var(--text-muted)] text-xs">
                  total return
                </span>
              </span>
            ) : (
              <span className="text-sm text-[var(--text-muted)]">
                No return data
              </span>
            )}
          </div>
        </div>

        {/* Summary Metrics */}
        <div className="flex flex-wrap gap-4">
          <MetricPill
            icon={<Banknote size={14} />}
            label="Cash"
            value={`$${(portfolio?.cash ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          />
          <MetricPill
            icon={<BarChart3 size={14} />}
            label="Positions"
            value={String(portfolio?.positions_count ?? 0)}
          />
          <MetricPill
            icon={<Wallet size={14} />}
            label="Total Value"
            value={`$${(portfolio?.total_value ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          />
        </div>
      </div>
    </div>
  );
}

function MetricPill({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex flex-col rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-2 min-w-[120px]">
      <p className="text-xs text-[var(--text-muted)] flex items-center gap-1.5 mb-0.5">
        {icon}
        {label}
      </p>
      <p className="text-sm font-semibold font-mono-nums tabular-nums text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
