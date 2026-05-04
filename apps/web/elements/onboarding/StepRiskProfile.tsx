"use client";

import { useState } from "react";
import { useSetRiskProfile } from "@/lib/queries/useOnboarding";

interface StepRiskProfileProps {
  onComplete: () => void;
  onError: (message: string) => void;
}

export function StepRiskProfile({ onComplete, onError }: StepRiskProfileProps) {
  const [volLow, setVolLow] = useState("0.10");
  const [volHigh, setVolHigh] = useState("0.20");
  const [ddCeiling, setDdCeiling] = useState("0.10");
  const [concCap, setConcCap] = useState("0.10");
  const mutation = useSetRiskProfile();

  function handleSubmit() {
    onError("");
    mutation.mutate(
      {
        vol_target_low: parseFloat(volLow),
        vol_target_high: parseFloat(volHigh),
        drawdown_ceiling: parseFloat(ddCeiling),
        concentration_cap: parseFloat(concCap),
      },
      {
        onSuccess: () => onComplete(),
        onError: (err: Error) =>
          onError(err instanceof Error ? err.message : "Save failed"),
      },
    );
  }

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
      <div className="space-y-1">
        <h2 className="text-base font-medium text-[var(--text-primary)]">
          Step 2: Define Your Risk Tolerance
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Set boundaries for how much risk the assistant can take. These
          constraints are enforced by the compliance engine on every trade.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="block text-sm text-[var(--text-secondary)]">
            Vol Target (Low)
          </label>
          <input
            type="number"
            step="0.01"
            min="0.01"
            max="0.99"
            value={volLow}
            onChange={(e) => setVolLow(e.target.value)}
            className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
            disabled={mutation.isPending}
          />
          <p className="text-xs text-[var(--text-muted)]">
            Minimum volatility (0.01 - 0.99)
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-sm text-[var(--text-secondary)]">
            Vol Target (High)
          </label>
          <input
            type="number"
            step="0.01"
            min="0.02"
            max="1.0"
            value={volHigh}
            onChange={(e) => setVolHigh(e.target.value)}
            className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
            disabled={mutation.isPending}
          />
          <p className="text-xs text-[var(--text-muted)]">
            Maximum volatility (0.02 - 1.0)
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-sm text-[var(--text-secondary)]">
            Max Drawdown Ceiling
          </label>
          <input
            type="number"
            step="0.01"
            min="0.05"
            max="0.30"
            value={ddCeiling}
            onChange={(e) => setDdCeiling(e.target.value)}
            className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
            disabled={mutation.isPending}
          />
          <p className="text-xs text-[var(--text-muted)]">5% - 30%</p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-sm text-[var(--text-secondary)]">
            Concentration Cap
          </label>
          <input
            type="number"
            step="0.01"
            min="0.01"
            max="0.50"
            value={concCap}
            onChange={(e) => setConcCap(e.target.value)}
            className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
            disabled={mutation.isPending}
          />
          <p className="text-xs text-[var(--text-muted)]">
            1% - 50% per position
          </p>
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={mutation.isPending}
        className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-4 py-3 text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity min-h-12"
      >
        {mutation.isPending ? "Saving..." : "Save Risk Profile"}
      </button>
    </div>
  );
}
