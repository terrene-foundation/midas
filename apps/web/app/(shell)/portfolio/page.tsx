"use client";

import {
  usePortfolio,
  usePositions,
  useAllocation,
} from "@/lib/queries/usePortfolio";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { PortfolioRowSkeleton, Skeleton } from "@/elements/LoadingSkeleton";

export default function PortfolioPage() {
  const { data: portfolio, isPending: portfolioLoading } = usePortfolio();
  const { data: positionsData, isPending: positionsLoading } = usePositions();
  const { data: allocationData } = useAllocation();

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">
        Portfolio
      </h1>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {portfolioLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} variant="rect" className="h-20" />
          ))
        ) : (
          <>
            <MetricCard
              label="Total Value"
              value={`$${(portfolio?.total_value ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
            />
            <MetricCard
              label="NAV"
              value={`$${(portfolio?.nav ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
            />
            <MetricCard
              label="Cash"
              value={`$${(portfolio?.cash ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
            />
            <MetricCard
              label="Positions"
              value={String(portfolio?.positions_count ?? 0)}
            />
          </>
        )}
      </div>

      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)]">
        <div className="px-4 py-3 border-b border-[var(--border-default)]">
          <h2 className="text-sm font-medium text-[var(--text-secondary)]">
            Positions
          </h2>
        </div>
        {positionsLoading ? (
          <div className="p-4 space-y-2">
            <PortfolioRowSkeleton />
            <PortfolioRowSkeleton />
            <PortfolioRowSkeleton />
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-default)]">
            {(positionsData?.positions ?? []).map((p) => (
              <div
                key={p.ticker}
                className="flex items-center justify-between px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-[var(--bg-elevated)] flex items-center justify-center text-xs font-medium text-[var(--text-primary)]">
                    {p.ticker.slice(0, 2)}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">
                      {p.ticker}
                    </p>
                    <p className="text-xs text-[var(--text-muted)]">
                      {p.quantity} shares
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-6 text-right">
                  <div>
                    <p className="text-sm font-mono-nums tabular-nums text-[var(--text-primary)]">
                      $
                      {p.market_value.toLocaleString("en-US", {
                        minimumFractionDigits: 2,
                      })}
                    </p>
                    <FinancialFigure
                      value={p.unrealized_pnl_pct}
                      format="percent"
                      className="text-xs"
                    />
                  </div>
                  <div className="w-16 text-right">
                    <p className="text-xs text-[var(--text-muted)]">Weight</p>
                    <p className="text-xs font-mono-nums tabular-nums text-[var(--text-secondary)]">
                      {(p.weight * 100).toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>
            ))}
            {!positionsData?.positions?.length && (
              <p className="text-sm text-[var(--text-muted)] text-center py-8">
                No positions
              </p>
            )}
          </div>
        )}
      </div>

      {allocationData && allocationData.allocations.length > 0 && (
        <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
            Allocation
          </h2>
          <div className="space-y-2">
            {allocationData.allocations.map((a) => (
              <div key={a.category} className="flex items-center gap-3">
                <span className="text-sm text-[var(--text-primary)] w-32">
                  {a.category}
                </span>
                <div className="flex-1 h-2 rounded-full bg-[var(--bg-elevated)]">
                  <div
                    className="h-full rounded-full bg-[var(--accent-gold)] transition-all"
                    style={{ width: `${a.weight * 100}%` }}
                  />
                </div>
                <span className="text-xs font-mono-nums tabular-nums text-[var(--text-secondary)] w-12 text-right">
                  {(a.weight * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className="text-lg font-semibold font-mono-nums tabular-nums text-[var(--text-primary)] mt-1">
        {value}
      </p>
    </div>
  );
}
