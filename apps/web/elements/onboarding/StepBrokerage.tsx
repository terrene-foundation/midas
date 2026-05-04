"use client";

import { useState } from "react";
import { useConnectBrokerage } from "@/lib/queries/useOnboarding";

interface StepBrokerageProps {
  onComplete: () => void;
  onError: (message: string) => void;
}

export function StepBrokerage({ onComplete, onError }: StepBrokerageProps) {
  const [connectionRef, setConnectionRef] = useState("");
  const mutation = useConnectBrokerage();

  const isFormValid = connectionRef.trim().length > 0;

  function handleSubmit() {
    if (!isFormValid) {
      onError("Connection reference is required");
      return;
    }
    onError("");
    mutation.mutate(
      { connection_ref: connectionRef.trim() },
      {
        onSuccess: () => onComplete(),
        onError: (err: Error) =>
          onError(err instanceof Error ? err.message : "Connection failed"),
      },
    );
  }

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
      <div className="space-y-1">
        <h2 className="text-base font-medium text-[var(--text-primary)]">
          Step 1: Connect Your Brokerage
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          Link your brokerage account so the assistant can manage your
          portfolio. Your credentials are encrypted and never stored in
          plaintext.
        </p>
      </div>

      <div>
        <label className="block text-sm text-[var(--text-secondary)] mb-1.5">
          Connection Reference
        </label>
        <input
          type="text"
          value={connectionRef}
          onChange={(e) => setConnectionRef(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          placeholder="e.g., ibkr-account-XXXXX"
          className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
          disabled={mutation.isPending}
        />
        <p className="mt-1.5 text-xs text-[var(--text-muted)]">
          Enter your brokerage account ID or API reference from your broker
          dashboard.
        </p>
      </div>

      <button
        onClick={handleSubmit}
        disabled={!isFormValid || mutation.isPending}
        className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-4 py-3 text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity min-h-12"
      >
        {mutation.isPending ? "Connecting..." : "Connect Brokerage"}
      </button>
    </div>
  );
}
