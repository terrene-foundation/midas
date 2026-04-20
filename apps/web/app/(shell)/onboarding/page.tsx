"use client";

import { useState } from "react";
import { api } from "@/lib/api-client";

type Step = "connect" | "risk" | "universe" | "activate" | "done";

const STEPS: { key: Step; label: string; n: number }[] = [
  { key: "connect", label: "Connect Brokerage", n: 1 },
  { key: "risk", label: "Risk Profile", n: 2 },
  { key: "universe", label: "Universe Constraints", n: 3 },
  { key: "activate", label: "Activate", n: 4 },
];

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>("connect");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Connect step
  const [connectionRef, setConnectionRef] = useState("");

  // Risk step
  const [volLow, setVolLow] = useState("0.10");
  const [volHigh, setVolHigh] = useState("0.20");
  const [ddCeiling, setDdCeiling] = useState("0.10");
  const [concCap, setConcCap] = useState("0.10");

  // Universe step
  const [excludeTickers, setExcludeTickers] = useState("");

  async function submitConnect() {
    setError("");
    setLoading(true);
    try {
      await api.post("/onboarding/connect-brokerage", {
        connection_ref: connectionRef,
      });
      setStep("risk");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Connection failed");
    } finally {
      setLoading(false);
    }
  }

  async function submitRisk() {
    setError("");
    setLoading(true);
    try {
      await api.post("/onboarding/risk-profile", {
        vol_target_low: parseFloat(volLow),
        vol_target_high: parseFloat(volHigh),
        drawdown_ceiling: parseFloat(ddCeiling),
        concentration_cap: parseFloat(concCap),
      });
      setStep("universe");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setLoading(false);
    }
  }

  async function submitUniverse() {
    setError("");
    setLoading(true);
    try {
      const exclusions = excludeTickers
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await api.post("/onboarding/universe-constraints", {
        universe_exclusions: exclusions,
      });
      setStep("activate");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setLoading(false);
    }
  }

  async function submitActivate() {
    setError("");
    setLoading(true);
    try {
      await api.post("/onboarding/activate");
      setStep("done");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Activation failed");
    } finally {
      setLoading(false);
    }
  }

  const stepIndex = STEPS.findIndex((s) => s.key === step);
  const progress =
    step === "done" ? 100 : Math.round((stepIndex / STEPS.length) * 100);

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">
        Set Up Your Investment Assistant
      </h1>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--accent-gold)] transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-[var(--text-muted)]">
          {STEPS.map((s) => (
            <span
              key={s.key}
              className={
                STEPS.findIndex((x) => x.key === step) >=
                STEPS.findIndex((x) => x.key === s.key)
                  ? "text-[var(--text-primary)] font-medium"
                  : ""
              }
            >
              {s.n}. {s.label}
            </span>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-[var(--radius)] border border-[var(--loss-red)]/30 bg-[var(--loss-red)]/5 p-3 text-sm text-[var(--loss-red)]">
          {error}
        </div>
      )}

      {/* Step 1: Connect Brokerage */}
      {step === "connect" && (
        <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
          <h2 className="text-base font-medium text-[var(--text-primary)]">
            Step 1: Connect Your Brokerage
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            Link your brokerage account so the assistant can manage your
            portfolio. Your credentials are encrypted and never stored in
            plaintext.
          </p>
          <div>
            <label className="block text-sm text-[var(--text-secondary)] mb-1">
              Connection Reference
            </label>
            <input
              type="text"
              value={connectionRef}
              onChange={(e) => setConnectionRef(e.target.value)}
              placeholder="e.g., ibkr-account-XXXXX"
              className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
            />
          </div>
          <button
            onClick={submitConnect}
            disabled={!connectionRef || loading}
            className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-4 py-2 text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            {loading ? "Connecting..." : "Connect Brokerage"}
          </button>
        </div>
      )}

      {/* Step 2: Risk Profile */}
      {step === "risk" && (
        <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
          <h2 className="text-base font-medium text-[var(--text-primary)]">
            Step 2: Define Your Risk Tolerance
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            Set boundaries for how much risk the assistant can take. These
            constraints are enforced by the compliance engine on every trade.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-1">
                Vol Target (Low)
              </label>
              <input
                type="number"
                step="0.01"
                value={volLow}
                onChange={(e) => setVolLow(e.target.value)}
                className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-1">
                Vol Target (High)
              </label>
              <input
                type="number"
                step="0.01"
                value={volHigh}
                onChange={(e) => setVolHigh(e.target.value)}
                className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-1">
                Max Drawdown Ceiling
              </label>
              <input
                type="number"
                step="0.01"
                value={ddCeiling}
                onChange={(e) => setDdCeiling(e.target.value)}
                className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-1">
                Concentration Cap
              </label>
              <input
                type="number"
                step="0.01"
                value={concCap}
                onChange={(e) => setConcCap(e.target.value)}
                className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
              />
            </div>
          </div>
          <button
            onClick={submitRisk}
            disabled={loading}
            className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-4 py-2 text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            {loading ? "Saving..." : "Save Risk Profile"}
          </button>
        </div>
      )}

      {/* Step 3: Universe Constraints */}
      {step === "universe" && (
        <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
          <h2 className="text-base font-medium text-[var(--text-primary)]">
            Step 3: Set Universe Constraints
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            Optionally exclude specific tickers from the investment universe.
            The assistant will never trade excluded instruments.
          </p>
          <div>
            <label className="block text-sm text-[var(--text-secondary)] mb-1">
              Excluded Tickers (comma-separated)
            </label>
            <input
              type="text"
              value={excludeTickers}
              onChange={(e) => setExcludeTickers(e.target.value)}
              placeholder="e.g., TSLA, COIN, MSTR"
              className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
            />
          </div>
          <button
            onClick={submitUniverse}
            disabled={loading}
            className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-4 py-2 text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            {loading ? "Saving..." : "Save Constraints"}
          </button>
        </div>
      )}

      {/* Step 4: Activate */}
      {step === "activate" && (
        <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
          <h2 className="text-base font-medium text-[var(--text-primary)]">
            Step 4: Activate Paper Trading
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            Your assistant is ready to start. It will begin in paper trading
            mode so you can observe its decisions before going live.
          </p>
          <button
            onClick={submitActivate}
            disabled={loading}
            className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-4 py-2 text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
          >
            {loading ? "Activating..." : "Activate Paper Trading"}
          </button>
        </div>
      )}

      {/* Done */}
      {step === "done" && (
        <div className="rounded-[var(--radius)] border border-[var(--gain-green)]/30 bg-[var(--gain-green)]/5 p-6 text-center space-y-3">
          <h2 className="text-base font-medium text-[var(--gain-green)]">
            Setup Complete
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            Your investment assistant is now active in paper trading mode. Visit
            the Pulse dashboard to monitor its decisions.
          </p>
          <a
            href="/pulse"
            className="inline-block rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-6 py-2 text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Go to Dashboard
          </a>
        </div>
      )}
    </div>
  );
}
