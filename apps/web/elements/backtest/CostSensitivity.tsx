"use client";

import { useState } from "react";
import { FinancialFigure } from "@/elements/FinancialFigure";

interface CostSensitivityProps {
  // baseReturn and costDrag come from the backtest result
  baseReturn?: number | null;
  costDrag?: number | null;
}

export function CostSensitivity({
  baseReturn,
  costDrag,
}: CostSensitivityProps) {
  const [costBps, setCostBps] = useState(10); // default 10 bps

  // Compute impact: cost sensitivity = how much return changes per basis point of transaction cost
  const base = baseReturn ?? 0;
  const drag = costDrag ?? 0;
  const costMultiplier = drag !== 0 ? drag / costBps : 0;
  const simulatedDrag = costBps * costMultiplier;

  const returnWithSimulatedCost = base - simulatedDrag;
  const impact = simulatedDrag;

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-3">
        Cost Sensitivity
      </p>

      <div className="space-y-4">
        {/* Slider */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--text-secondary)]">
              Transaction cost
            </span>
            <span className="text-sm font-mono-nums tabular-nums text-[var(--accent-gold)]">
              {costBps} bps
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={costBps}
            onChange={(e) => setCostBps(Number(e.target.value))}
            className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--accent-gold)] bg-[var(--bg-elevated)]"
          />
          <div className="flex justify-between text-xs text-[var(--text-muted)]">
            <span>0 bps</span>
            <span>50 bps</span>
            <span>100 bps</span>
          </div>
        </div>

        {/* Impact breakdown */}
        <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] p-3 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--text-secondary)]">Base return</span>
            <FinancialFigure
              value={(baseReturn ?? 0) * 100}
              format="percent"
              showSign
              className="text-sm"
            />
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--text-secondary)]">
              Cost drag ({costBps} bps)
            </span>
            <span className="text-[var(--loss-red)] font-mono-nums tabular-nums">
              {impact >= 0 ? "-" : "+"}
              {Math.abs(impact * 100).toFixed(2)}%
            </span>
          </div>
          <div className="border-t border-[var(--border-default)] pt-2 flex items-center justify-between">
            <span className="text-sm font-medium text-[var(--text-primary)]">
              Return w/ costs
            </span>
            <FinancialFigure
              value={returnWithSimulatedCost * 100}
              format="percent"
              showSign
              className="text-sm font-semibold"
            />
          </div>
        </div>

        <p className="text-xs text-[var(--text-muted)]">
          Drag the slider to see how varying transaction costs affect realized
          returns.
        </p>
      </div>
    </div>
  );
}
