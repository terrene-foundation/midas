"use client";

import { FinancialFigure } from "@/elements/FinancialFigure";
import { cn } from "@/elements/ui/utils";
import type { Position } from "@/lib/types";
import { ArrowUpDown } from "lucide-react";

const DRIFT_THRESHOLD = 0.02;

interface PositionRowProps {
  position: Position;
  onClick?: () => void;
}

export function PositionRow({ position, onClick }: PositionRowProps) {
  const isDriftOverThreshold =
    Math.abs(position.drift_from_target) > DRIFT_THRESHOLD;

  return (
    <div
      onClick={onClick}
      className={cn(
        "flex items-center justify-between px-4 py-3 border-b border-[var(--border-default)] last:border-0 transition-colors cursor-pointer",
        onClick && "hover:bg-[var(--bg-hover)]",
      )}
    >
      {/* Left: ticker + quantity */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-9 h-9 rounded-full bg-[var(--bg-elevated)] flex items-center justify-center text-xs font-medium text-[var(--text-primary)] shrink-0">
          {position.ticker.slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-[var(--text-primary)] truncate">
            {position.ticker}
          </p>
          <p className="text-xs text-[var(--text-muted)]">
            {position.quantity.toLocaleString("en-US")} shares
          </p>
        </div>
      </div>

      {/* Right: metrics */}
      <div className="flex items-center gap-6">
        {/* Market value */}
        <div className="hidden sm:block text-right min-w-[90px]">
          <p className="text-sm font-mono-nums tabular-nums text-[var(--text-primary)]">
            $
            {position.market_value.toLocaleString("en-US", {
              minimumFractionDigits: 2,
            })}
          </p>
          <p className="text-xs text-[var(--text-muted)]">Market Value</p>
        </div>

        {/* Unrealized P&L */}
        <div className="text-right min-w-[80px]">
          <FinancialFigure
            value={position.unrealized_pnl}
            format="currency"
            showSign
            className="text-sm"
          />
          <FinancialFigure
            value={position.unrealized_pnl_pct * 100}
            format="percent"
            showSign
            className="text-xs"
          />
        </div>

        {/* Weight */}
        <div className="hidden md:block text-right min-w-[60px]">
          <p className="text-sm font-mono-nums tabular-nums text-[var(--text-secondary)]">
            {(position.weight * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-[var(--text-muted)]">Weight</p>
        </div>

        {/* Drift */}
        <div className="text-right min-w-[70px]">
          {isDriftOverThreshold ? (
            <>
              <FinancialFigure
                value={position.drift_from_target * 100}
                format="percent"
                showSign
                className="text-sm"
              />
              <p className="text-xs text-[var(--loss-red)]">drift</p>
            </>
          ) : (
            <p className="text-sm font-mono-nums tabular-nums text-[var(--text-muted)]">
              {(position.drift_from_target * 100).toFixed(1)}%
            </p>
          )}
        </div>

        {onClick && (
          <ArrowUpDown
            size={14}
            className="text-[var(--text-muted)] shrink-0"
          />
        )}
      </div>
    </div>
  );
}
