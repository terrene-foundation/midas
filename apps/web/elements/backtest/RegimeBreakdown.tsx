"use client";

import { FinancialFigure } from "@/elements/FinancialFigure";
import { cn } from "@/elements/ui/utils";

// Regime breakdown data — in v1 this comes from a dedicated API endpoint.
// Shape defined per spec 09 S9.2 for z_t-analogue periods.
interface RegimePeriod {
  period: string;
  start_date: string;
  end_date: string;
  return: number | null;
  sharpe: number | null;
  max_drawdown: number | null;
  period_count: number;
}

interface RegimeBreakdownProps {
  periods?: RegimePeriod[];
}

const REGIME_LABELS: Record<string, string> = {
  calm: "Calm",
  elevated: "Elevated",
  urgent: "Urgent",
  crisis: "Crisis",
};

export function RegimeBreakdown({ periods }: RegimeBreakdownProps) {
  if (!periods || periods.length === 0) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Regime Breakdown
        </p>
        <div className="text-center py-6">
          <p className="text-sm text-[var(--text-muted)]">
            No regime data available
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-3">
        Regime Breakdown
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-default)]">
              <th className="text-left py-2 px-2 text-xs text-[var(--text-muted)] font-medium">
                Period
              </th>
              <th className="text-right py-2 px-2 text-xs text-[var(--text-muted)] font-medium">
                Dates
              </th>
              <th className="text-right py-2 px-2 text-xs text-[var(--text-muted)] font-medium">
                Return
              </th>
              <th className="text-right py-2 px-2 text-xs text-[var(--text-muted)] font-medium">
                Sharpe
              </th>
              <th className="text-right py-2 px-2 text-xs text-[var(--text-muted)] font-medium">
                Max DD
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-default)]">
            {periods.map((period, i) => (
              <tr
                key={i}
                className="hover:bg-[var(--bg-hover)] transition-colors"
              >
                <td className="py-2.5 px-2">
                  <span
                    className={cn(
                      "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
                      period.period === "calm"
                        ? "bg-[var(--gain-green)]/10 text-[var(--gain-green)]"
                        : period.period === "elevated"
                          ? "bg-[var(--accent-gold)]/10 text-[var(--accent-gold)]"
                          : period.period === "urgent"
                            ? "bg-[var(--regime-urgent)]/10 text-[var(--regime-urgent)]"
                            : period.period === "crisis"
                              ? "bg-[var(--loss-red)]/10 text-[var(--loss-red)]"
                              : "bg-[var(--bg-elevated)] text-[var(--text-secondary)]",
                    )}
                  >
                    {REGIME_LABELS[period.period] ?? period.period}
                  </span>
                </td>
                <td className="py-2.5 px-2 text-right text-xs text-[var(--text-muted)] font-mono-nums tabular-nums">
                  {period.start_date
                    ? new Date(period.start_date).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })
                    : "—"}
                  {" – "}
                  {period.end_date
                    ? new Date(period.end_date).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })
                    : "—"}
                </td>
                <td className="py-2.5 px-2 text-right">
                  {period.return != null ? (
                    <FinancialFigure
                      value={period.return * 100}
                      format="percent"
                      showSign
                      className="text-sm"
                    />
                  ) : (
                    <span className="text-[var(--text-muted)]">—</span>
                  )}
                </td>
                <td className="py-2.5 px-2 text-right font-mono-nums tabular-nums text-[var(--text-secondary)]">
                  {period.sharpe != null ? period.sharpe.toFixed(2) : "—"}
                </td>
                <td className="py-2.5 px-2 text-right">
                  {period.max_drawdown != null ? (
                    <FinancialFigure
                      value={period.max_drawdown * 100}
                      format="percent"
                      className="text-sm"
                    />
                  ) : (
                    <span className="text-[var(--text-muted)]">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
