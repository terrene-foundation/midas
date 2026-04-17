"use client";

import type { PulseResponse } from "@/lib/types";
import { RegimeGauge } from "@/elements/regime/RegimeGauge";
import { useRegimeStore } from "@/stores/regime-store";
import {
  useDecisions,
  useApproveDecision,
  useDeclineDecision,
} from "@/lib/queries/useDecisions";
import { DecisionCardSkeleton } from "@/elements/LoadingSkeleton";
import { useState } from "react";
import { ReAuthModal } from "@/elements/ReAuthModal";
import { useKillSwitchStore } from "@/stores/kill-switch-store";
import { useActivateKillSwitch } from "@/lib/queries/useCompliance";

interface PulseCrisisLayoutProps {
  pulse: PulseResponse | undefined;
}

export function PulseCrisisLayout({ pulse }: PulseCrisisLayoutProps) {
  const { a_t } = useRegimeStore();
  const killSwitchActive = useKillSwitchStore((s) => s.isActive);
  const setLocalKillSwitch = useKillSwitchStore((s) => s.setActive);
  const activateKillSwitch = useActivateKillSwitch();
  const { data: decisionsData, isPending } = useDecisions("pending");
  const approve = useApproveDecision();
  const decline = useDeclineDecision();
  const [reAuthFor, setReAuthFor] = useState<string | null>(null);
  const nav = pulse?.nav ?? 0;

  const focusDecision = decisionsData?.decisions?.[0];

  return (
    <div className="p-6 space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-[var(--loss-red)] animate-pulse" />
          <span className="text-sm font-semibold text-[var(--loss-red)]">
            CRISIS MODE
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-mono-nums tabular-nums text-[var(--text-secondary)]">
            ${nav.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </span>
          <button
            onClick={() =>
              activateKillSwitch.mutate("Crisis mode activation", {
                onSuccess: () => setLocalKillSwitch(),
              })
            }
            className="px-3 py-1.5 rounded-[var(--radius)] bg-[var(--loss-red)] text-white text-xs font-semibold hover:brightness-110 transition-all"
          >
            Kill Switch
          </button>
        </div>
      </div>

      <RegimeGauge a_t={a_t} size="lg" />

      {killSwitchActive && (
        <div className="rounded-[var(--radius)] border-2 border-[var(--loss-red)] bg-[var(--loss-red)]/10 p-4 text-center">
          <p className="text-lg font-semibold text-[var(--loss-red)]">
            ALL TRADING PAUSED
          </p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            Autonomous decisioning halted. Monitoring continues.
          </p>
        </div>
      )}

      {!killSwitchActive && (
        <>
          {isPending ? (
            <DecisionCardSkeleton />
          ) : focusDecision ? (
            <div className="rounded-[var(--radius)] border-2 border-[var(--loss-red)] bg-[var(--bg-surface)] p-6 space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                  {focusDecision.instruments || focusDecision.decision_type}
                </h2>
                <p className="text-sm text-[var(--text-secondary)] mt-1">
                  {focusDecision.action} &middot;{" "}
                  {(focusDecision.confidence * 100).toFixed(0)}% confidence
                </p>
              </div>

              <div className="w-full h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-[var(--loss-red)] transition-all duration-1000"
                  style={{ width: "80%" }}
                />
              </div>

              <div className="flex flex-col gap-4 pt-2">
                <button
                  onClick={() => setReAuthFor(focusDecision.id)}
                  className="w-full py-3 rounded-[var(--radius)] bg-[var(--gain-green)] text-white font-medium hover:brightness-110 transition-all"
                >
                  Approve
                </button>
                <div className="flex justify-end">
                  <button
                    onClick={() => decline.mutate(focusDecision.id)}
                    className="px-6 py-2 rounded-[var(--radius)] border border-[var(--loss-red)]/50 text-[var(--loss-red)] text-sm hover:bg-[var(--loss-red)]/10 transition-colors"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-[var(--text-muted)]">
              No pending decisions
            </p>
          )}
        </>
      )}

      <ReAuthModal
        open={!!reAuthFor}
        reason="Crisis-mode approval requires confirmation"
        onResult={(ok) => {
          if (ok && reAuthFor) approve.mutate(reAuthFor);
          setReAuthFor(null);
        }}
      />
    </div>
  );
}
