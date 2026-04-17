"use client";

import type { PulseResponse } from "@/lib/types";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { RegimeGauge } from "@/elements/regime/RegimeGauge";
import { useRegimeStore } from "@/stores/regime-store";

interface PulseCalmLayoutProps {
  pulse: PulseResponse | undefined;
}

export function PulseCalmLayout({ pulse }: PulseCalmLayoutProps) {
  const { a_t, changepointProbability } = useRegimeStore();
  const nav = pulse?.nav ?? 0;
  const changePct = pulse?.nav_change_pct ?? 0;
  const positions = pulse?.positions_summary ?? [];

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div className="space-y-1">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
            Portfolio Value
          </p>
          <p className="text-4xl font-semibold font-mono-nums tabular-nums text-[var(--text-primary)]">
            ${nav.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
          <FinancialFigure
            value={changePct}
            format="percent"
            className="text-sm"
          />
        </div>
        <div className="w-48 space-y-2">
          <RegimeGauge
            a_t={a_t}
            transitionPressure={changepointProbability}
            size="sm"
          />
          <p className="text-xs text-[var(--text-muted)] text-right">
            Market: Calm
          </p>
        </div>
      </div>

      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
          Positions
        </h3>
        {positions.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">No positions</p>
        ) : (
          <div className="space-y-2">
            {positions.slice(0, 5).map((p) => (
              <div key={p.ticker} className="flex justify-between text-sm">
                <span className="text-[var(--text-primary)]">{p.ticker}</span>
                <span className="font-mono-nums tabular-nums text-[var(--text-secondary)]">
                  $
                  {p.market_value.toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                  })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
