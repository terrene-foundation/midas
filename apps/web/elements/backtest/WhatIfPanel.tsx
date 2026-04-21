"use client";

import { useState } from "react";
import { cn } from "@/elements/ui/utils";
import type { EnvelopeConfig } from "@/lib/types";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { Play, SlidersHorizontal } from "lucide-react";

interface WhatIfPanelProps {
  currentEnvelope?: EnvelopeConfig | null;
  onSimulate?: (config: EnvelopeConfig) => void;
}

export function WhatIfPanel({ currentEnvelope, onSimulate }: WhatIfPanelProps) {
  const [volLow, setVolLow] = useState(currentEnvelope?.vol_target_low ?? 0.05);
  const [volHigh, setVolHigh] = useState(
    currentEnvelope?.vol_target_high ?? 0.15,
  );
  const [drawdownCeiling, setDrawdownCeiling] = useState(
    currentEnvelope?.drawdown_ceiling ?? 0.2,
  );
  const [concentrationCap, setConcentrationCap] = useState(
    currentEnvelope?.concentration_cap ?? 0.05,
  );
  const [submitted, setSubmitted] = useState(false);

  const handleSimulate = () => {
    const config: EnvelopeConfig = {
      vol_target_low: volLow,
      vol_target_high: volHigh,
      drawdown_ceiling: drawdownCeiling,
      concentration_cap: concentrationCap,
    };
    onSimulate?.(config);
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 2000);
  };

  const isModified =
    volLow !== (currentEnvelope?.vol_target_low ?? 0.05) ||
    volHigh !== (currentEnvelope?.vol_target_high ?? 0.15) ||
    drawdownCeiling !== (currentEnvelope?.drawdown_ceiling ?? 0.2) ||
    concentrationCap !== (currentEnvelope?.concentration_cap ?? 0.05);

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <div className="flex items-center gap-2 mb-4">
        <SlidersHorizontal size={14} className="text-[var(--text-muted)]" />
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
          What-If Envelope
        </p>
      </div>

      <div className="space-y-4">
        {/* Vol Target Range */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--text-secondary)]">
              Vol target low
            </span>
            <span className="text-sm font-mono-nums tabular-nums text-[var(--accent-gold)]">
              {(volLow * 100).toFixed(1)}%
            </span>
          </div>
          <input
            type="range"
            min={0.01}
            max={0.2}
            step={0.005}
            value={volLow}
            onChange={(e) => setVolLow(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent-gold)] bg-[var(--bg-elevated)]"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--text-secondary)]">
              Vol target high
            </span>
            <span className="text-sm font-mono-nums tabular-nums text-[var(--accent-gold)]">
              {(volHigh * 100).toFixed(1)}%
            </span>
          </div>
          <input
            type="range"
            min={0.01}
            max={0.3}
            step={0.005}
            value={volHigh}
            onChange={(e) => setVolHigh(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent-gold)] bg-[var(--bg-elevated)]"
          />
        </div>

        {/* Drawdown Ceiling */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--text-secondary)]">
              Drawdown ceiling
            </span>
            <span className="text-sm font-mono-nums tabular-nums text-[var(--loss-red)]">
              {(drawdownCeiling * 100).toFixed(1)}%
            </span>
          </div>
          <input
            type="range"
            min={0.05}
            max={0.5}
            step={0.01}
            value={drawdownCeiling}
            onChange={(e) => setDrawdownCeiling(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--loss-red)] bg-[var(--bg-elevated)]"
          />
        </div>

        {/* Concentration Cap */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--text-secondary)]">
              Concentration cap
            </span>
            <span className="text-sm font-mono-nums tabular-nums text-[var(--accent-gold)]">
              {(concentrationCap * 100).toFixed(1)}%
            </span>
          </div>
          <input
            type="range"
            min={0.01}
            max={0.3}
            step={0.005}
            value={concentrationCap}
            onChange={(e) => setConcentrationCap(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent-gold)] bg-[var(--bg-elevated)]"
          />
        </div>

        {/* Simulate Button */}
        <button
          onClick={handleSimulate}
          disabled={!isModified}
          className={cn(
            "w-full flex items-center justify-center gap-2 rounded-[var(--radius)] py-2.5 text-sm font-medium transition-all",
            isModified
              ? "bg-[var(--accent-gold)] text-[#0F1117] hover:bg-[var(--accent-gold-dim)]"
              : "bg-[var(--bg-elevated)] text-[var(--text-muted)] cursor-not-allowed",
          )}
        >
          <Play size={14} />
          {submitted ? "Simulating..." : "Run What-If"}
        </button>

        <p className="text-xs text-[var(--text-muted)] text-center">
          Adjust envelope parameters to see projected impact on backtest
          performance.
        </p>
      </div>
    </div>
  );
}
