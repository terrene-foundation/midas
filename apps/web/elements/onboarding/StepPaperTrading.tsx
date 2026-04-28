"use client";

import { useState } from "react";
import { api } from "@/lib/api-client";

interface StepPaperTradingProps {
  onComplete: () => void;
  onError: (message: string) => void;
}

export function StepPaperTrading({
  onComplete,
  onError,
}: StepPaperTradingProps) {
  const [loading, setLoading] = useState(false);
  const [excludeTickers, setExcludeTickers] = useState("");

  async function handleSubmit() {
    setLoading(true);
    onError("");
    try {
      const exclusions = excludeTickers
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await api.post("/onboarding/universe-constraints", {
        universe_exclusions: exclusions,
      });
      onComplete();
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
      <div className="space-y-1">
        <h2 className="text-base font-medium text-[var(--text-primary)]">
          Step 3: Set Universe Constraints
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Optionally exclude specific tickers from the investment universe. The
          assistant will never trade excluded instruments. Leave empty to
          include all available instruments.
        </p>
      </div>

      <div className="space-y-1.5">
        <label className="block text-sm text-[var(--text-secondary)]">
          Excluded Tickers
        </label>
        <input
          type="text"
          value={excludeTickers}
          onChange={(e) => setExcludeTickers(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          placeholder="e.g., TSLA, COIN, MSTR (comma-separated)"
          className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
          disabled={loading}
        />
        <p className="text-xs text-[var(--text-muted)]">
          Separate multiple tickers with commas. This step is optional.
        </p>
      </div>

      <button
        onClick={handleSubmit}
        disabled={loading}
        className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-4 py-2.5 text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
      >
        {loading ? "Saving..." : "Save Constraints"}
      </button>
    </div>
  );
}
