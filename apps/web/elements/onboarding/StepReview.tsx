"use client";

import { useState } from "react";
import { api } from "@/lib/api-client";

interface StepReviewProps {
  onComplete: () => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export function StepReview({ onComplete, onDone, onError }: StepReviewProps) {
  const [loading, setLoading] = useState(false);

  async function handleActivate() {
    setLoading(true);
    onError("");
    try {
      await api.post("/onboarding/activate");
      onComplete();
      // Short delay before redirecting to dashboard
      setTimeout(onDone, 1500);
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : "Activation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
      <div className="space-y-1">
        <h2 className="text-base font-medium text-[var(--text-primary)]">
          Step 4: Activate Paper Trading
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Your assistant is ready to start. It will begin in paper trading mode
          so you can observe its decisions before going live. No real funds will
          be used.
        </p>
      </div>

      <div className="rounded-[var(--radius)] border border-[var(--accent-gold)]/20 bg-[var(--accent-gold)]/5 p-4 space-y-2">
        <p className="text-sm font-medium text-[var(--text-primary)]">
          What happens next:
        </p>
        <ul className="space-y-1.5 text-sm text-[var(--text-secondary)]">
          <li className="flex items-start gap-2">
            <span className="text-[var(--accent-gold)]">1.</span>
            <span>
              The assistant will analyze your portfolio and market conditions
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-[var(--accent-gold)]">2.</span>
            <span>
              It will generate paper trade recommendations for your review
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-[var(--accent-gold)]">3.</span>
            <span>You can approve, modify, or decline each decision</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-[var(--accent-gold)]">4.</span>
            <span>
              After the paper period, you can transition to live trading
            </span>
          </li>
        </ul>
      </div>

      <button
        onClick={handleActivate}
        disabled={loading}
        className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-4 py-2.5 text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
      >
        {loading ? "Activating..." : "Activate Paper Trading"}
      </button>
    </div>
  );
}
