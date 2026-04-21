"use client";

import type { Position } from "@/lib/types";
import { FinancialFigure } from "@/elements/FinancialFigure";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/elements/ui/sheet";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { ExternalLink, TrendingUp, TrendingDown } from "lucide-react";

interface PositionDetailSheetProps {
  position: Position | null;
  onClose: () => void;
  // Placeholder for future data-fetching hooks
  // historyData, riskContribution, debateThreadId would come from dedicated hooks
}

export function PositionDetailSheet({
  position,
  onClose,
}: PositionDetailSheetProps) {
  return (
    <Sheet open={!!position} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-[400px] bg-[var(--bg-surface)] border-[var(--border-default)]"
      >
        {position ? (
          <>
            <SheetHeader className="border-b border-[var(--border-default)] pb-4">
              <SheetTitle className="text-[var(--text-primary)]">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-[var(--bg-elevated)] flex items-center justify-center text-sm font-medium text-[var(--text-primary)]">
                    {position.ticker.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <p className="text-lg font-semibold">{position.ticker}</p>
                    <p className="text-xs text-[var(--text-muted)] font-normal">
                      {position.quantity.toLocaleString("en-US")} shares
                    </p>
                  </div>
                </div>
              </SheetTitle>
            </SheetHeader>

            <div className="py-4 space-y-6">
              {/* Key Metrics */}
              <div className="grid grid-cols-2 gap-3">
                <DetailMetric
                  label="Avg Cost"
                  value={`$${(position.market_value / position.quantity / (1 + position.unrealized_pnl_pct)).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
                />
                <DetailMetric
                  label="Current Price"
                  value={`$${(position.market_value / position.quantity).toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
                />
                <DetailMetric
                  label="Market Value"
                  value={`$${position.market_value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
                />
                <DetailMetric
                  label="Unrealized P&L"
                  value={position.unrealized_pnl >= 0 ? "+" : ""}
                  children={
                    <div className="flex flex-col items-end">
                      <span className="text-lg font-semibold font-mono-nums tabular-nums">
                        <FinancialFigure
                          value={position.unrealized_pnl}
                          format="currency"
                          showSign
                        />
                      </span>
                      <span className="text-xs">
                        <FinancialFigure
                          value={position.unrealized_pnl_pct * 100}
                          format="percent"
                          showSign
                        />
                      </span>
                    </div>
                  }
                />
              </div>

              {/* Weight & Drift */}
              <div className="space-y-3">
                <h3 className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
                  Allocation
                </h3>
                <div className="grid grid-cols-2 gap-3">
                  <DetailMetric
                    label="Current Weight"
                    value={`${(position.weight * 100).toFixed(2)}%`}
                  />
                  <DetailMetric
                    label="Drift"
                    children={
                      <FinancialFigure
                        value={position.drift_from_target * 100}
                        format="percent"
                        showSign
                      />
                    }
                  />
                </div>
              </div>

              {/* Placeholder sections for future expansion */}
              <div className="space-y-3">
                <h3 className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
                  Position History
                </h3>
                <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4 text-center">
                  <p className="text-sm text-[var(--text-muted)]">
                    Historical price chart coming soon
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                <h3 className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
                  Risk Contribution
                </h3>
                <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-4 text-center">
                  <p className="text-sm text-[var(--text-muted)]">
                    Risk metrics coming soon
                  </p>
                </div>
              </div>

              {/* Links */}
              <div className="flex flex-col gap-2">
                <h3 className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
                  Related
                </h3>
                <button className="flex items-center justify-between rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors">
                  <span className="flex items-center gap-2">
                    <ExternalLink size={14} />
                    View Debate Thread
                  </span>
                  <span className="text-[var(--text-muted)]">→</span>
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="p-4 space-y-4">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-40 w-full" variant="card" />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

function DetailMetric({
  label,
  value,
  children,
}: {
  label: string;
  value?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3">
      <p className="text-xs text-[var(--text-muted)] mb-1">{label}</p>
      {children ?? (
        <p className="text-sm font-semibold font-mono-nums tabular-nums text-[var(--text-primary)]">
          {value}
        </p>
      )}
    </div>
  );
}
