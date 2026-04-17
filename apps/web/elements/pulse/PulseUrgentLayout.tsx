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

interface PulseUrgentLayoutProps {
  pulse: PulseResponse | undefined;
}

export function PulseUrgentLayout({ pulse }: PulseUrgentLayoutProps) {
  const { a_t } = useRegimeStore();
  const killSwitchActive = useKillSwitchStore((s) => s.isActive);
  const setLocalKillSwitch = useKillSwitchStore((s) => s.setActive);
  const activateKillSwitchApi = useActivateKillSwitch();
  const { data: decisionsData, isPending } = useDecisions("pending");
  const approve = useApproveDecision();
  const decline = useDeclineDecision();
  const [reAuthFor, setReAuthFor] = useState<string | null>(null);
  const nav = pulse?.nav ?? 0;

  const focusDecision = decisionsData?.decisions?.[0];
  const otherDecisions = decisionsData?.decisions?.slice(1) ?? [];

  const handleKillSwitch = () => {
    activateKillSwitchApi.mutate("Urgent mode activation", {
      onSuccess: () => setLocalKillSwitch(),
    });
  };

  return (
    <div className="p-6 space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <RegimeGauge a_t={a_t} size="md" className="max-w-xs" />
        <div className="flex items-center gap-3">
          <span className="text-sm text-[var(--text-secondary)]">
            ${nav.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </span>
          {killSwitchActive ? (
            <span className="px-2 py-1 text-xs font-semibold rounded bg-[var(--loss-red)] text-white">
              TRADING PAUSED
            </span>
          ) : (
            <button
              onClick={handleKillSwitch}
              className="px-2 py-1 text-xs font-medium rounded border border-[var(--loss-red)]/40 text-[var(--loss-red)] hover:bg-[var(--loss-red)]/10 transition-colors"
              aria-label="Activate kill switch"
            >
              Kill Switch
            </button>
          )}
        </div>
      </div>

      {killSwitchActive && (
        <div className="rounded-[var(--radius)] border-2 border-[var(--loss-red)] bg-[var(--loss-red)]/10 p-3 text-center">
          <p className="text-sm font-semibold text-[var(--loss-red)]">
            ALL TRADING PAUSED
          </p>
        </div>
      )}

      {!killSwitchActive && (
        <>
          {isPending ? (
            <DecisionCardSkeleton />
          ) : focusDecision ? (
            <div className="rounded-[var(--radius)] border-2 border-[var(--regime-urgent)] bg-[var(--bg-surface)] p-6 space-y-4">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                    {focusDecision.instruments || focusDecision.decision_type}
                  </h2>
                  <p className="text-sm text-[var(--text-secondary)] mt-1">
                    {focusDecision.action} &middot;{" "}
                    {(focusDecision.confidence * 100).toFixed(0)}% confidence
                  </p>
                </div>
              </div>

              <div className="w-full h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-[var(--regime-urgent)] transition-all duration-1000"
                  style={{ width: "65%" }}
                />
              </div>

              <div className="flex flex-col gap-3 pt-2">
                <button
                  onClick={() => setReAuthFor(focusDecision.id)}
                  className="w-full py-3 rounded-[var(--radius)] bg-[var(--gain-green)] text-white font-medium text-sm hover:brightness-110 transition-all"
                  aria-label="Approve decision"
                >
                  Approve
                </button>
                <div className="flex justify-end">
                  <button
                    onClick={() => decline.mutate(focusDecision.id)}
                    className="px-6 py-2 rounded-[var(--radius)] border border-[var(--loss-red)]/50 text-[var(--loss-red)] text-sm hover:bg-[var(--loss-red)]/10 transition-colors"
                    aria-label="Reject decision"
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

      {!killSwitchActive && otherDecisions.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
            Other Pending
          </h3>
          {otherDecisions.map((d) => (
            <div
              key={d.id}
              className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 flex justify-between"
            >
              <span className="text-sm text-[var(--text-primary)]">
                {d.instruments || d.decision_type}
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {d.action}
              </span>
            </div>
          ))}
        </div>
      )}

      <ReAuthModal
        open={!!reAuthFor}
        reason="Approving this decision requires confirmation"
        onResult={(ok) => {
          if (ok && reAuthFor) approve.mutate(reAuthFor);
          setReAuthFor(null);
        }}
      />
    </div>
  );
}
