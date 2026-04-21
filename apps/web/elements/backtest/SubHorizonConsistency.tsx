"use client";

import { FinancialFigure } from "@/elements/FinancialFigure";

interface SubHorizonConsistencyProps {
  horizons?: Array<{
    label: string;
    return: number | null;
    periods: number;
  }>;
}

export function SubHorizonConsistency({
  horizons,
}: SubHorizonConsistencyProps) {
  if (!horizons || horizons.length === 0) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Sub-Horizon Consistency
        </p>
        <div className="text-center py-6">
          <p className="text-sm text-[var(--text-muted)]">
            No sub-horizon data available
          </p>
        </div>
      </div>
    );
  }

  const maxReturn = Math.max(...horizons.map((h) => Math.abs(h.return ?? 0)));

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-3">
        Sub-Horizon Consistency
      </p>
      <div className="space-y-4">
        {horizons.map((h, i) => {
          const pct =
            maxReturn > 0 && h.return != null
              ? Math.abs(h.return) / maxReturn
              : 0;
          const isPositive = (h.return ?? 0) >= 0;

          return (
            <div key={i} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--text-primary)]">
                  {h.label}
                </span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[var(--text-muted)]">
                    {h.periods} periods
                  </span>
                  {h.return != null ? (
                    <FinancialFigure
                      value={h.return * 100}
                      format="percent"
                      showSign
                      className="text-sm"
                    />
                  ) : (
                    <span className="text-sm text-[var(--text-muted)]">—</span>
                  )}
                </div>
              </div>
              {/* Bar */}
              <div className="h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${isPositive ? "bg-[var(--gain-green)]" : "bg-[var(--loss-red)]"}`}
                  style={{ width: `${Math.max(pct * 100, 2)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-4 border-t border-[var(--border-default)]">
        <p className="text-xs text-[var(--text-muted)]">
          Shows consistency of returns across sub-horizons (e.g., monthly,
          quarterly, annual). Wider dispersion indicates return inconsistency.
        </p>
      </div>
    </div>
  );
}
