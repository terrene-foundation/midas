"use client";

import {
  useEnvelopeConfig,
  useAutonomyState,
  usePaperLiveState,
  useUpdateEnvelope,
} from "@/lib/queries/useSettings";
import {
  useComplianceRules,
  useKillSwitch,
  useClearKillSwitch,
} from "@/lib/queries/useCompliance";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { useState, useEffect, useRef } from "react";
import { PaperToLiveFlow } from "@/elements/safety/PaperToLiveFlow";
import { AttentionReport } from "@/elements/attention/AttentionReport";
import { NotificationPreferences } from "@/elements/settings/NotificationPreferences";
import {
  NotificationPermissionRequest,
  WeeklyAttentionSummary,
} from "@/elements/notifications";
import { cn } from "@/elements/ui/utils";

export default function SettingsPage() {
  const { data: envelope, isPending: envelopeLoading } = useEnvelopeConfig();
  const { data: autonomy, isPending: autonomyLoading } = useAutonomyState();
  const { data: paperLive } = usePaperLiveState();
  const { data: complianceData } = useComplianceRules();
  const updateEnvelope = useUpdateEnvelope();

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">
        Settings
      </h1>

      <section className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
        <h2 className="text-sm font-medium text-[var(--accent-gold)]">
          Risk Envelope
        </h2>
        {envelopeLoading ? (
          <Skeleton variant="rect" className="h-24" />
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <SettingField
              label="Vol Target Low"
              value={
                envelope
                  ? `${(envelope.vol_target_low * 100).toFixed(0)}%`
                  : "--"
              }
            />
            <SettingField
              label="Vol Target High"
              value={
                envelope
                  ? `${(envelope.vol_target_high * 100).toFixed(0)}%`
                  : "--"
              }
            />
            <SettingField
              label="Drawdown Ceiling"
              value={
                envelope
                  ? `${(envelope.drawdown_ceiling * 100).toFixed(0)}%`
                  : "--"
              }
            />
            <SettingField
              label="Concentration Cap"
              value={
                envelope
                  ? `${(envelope.concentration_cap * 100).toFixed(0)}%`
                  : "--"
              }
            />
          </div>
        )}
      </section>

      <section className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
        <h2 className="text-sm font-medium text-[var(--accent-gold)]">
          Autonomy
        </h2>
        {autonomyLoading ? (
          <Skeleton variant="rect" className="h-16" />
        ) : (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-[var(--text-secondary)]">Level</span>
              <span className="text-[var(--text-primary)] font-medium">
                L{autonomy?.level ?? 0} — {autonomy?.level_name ?? "Unknown"}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-[var(--text-secondary)]">Auto-approve</span>
              <span
                className={
                  autonomy?.can_auto_approve
                    ? "text-[var(--gain-green)]"
                    : "text-[var(--loss-red)]"
                }
              >
                {autonomy?.can_auto_approve ? "Yes" : "No"}
              </span>
            </div>
            {paperLive && (
              <div className="flex justify-between text-sm">
                <span className="text-[var(--text-secondary)]">Mode</span>
                <span className="text-[var(--text-primary)]">
                  {paperLive.mode === "live"
                    ? "Live"
                    : `Paper (${paperLive.days_in_paper}d)`}
                </span>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
        <h2 className="text-sm font-medium text-[var(--accent-gold)]">
          Compliance Rules
        </h2>
        {(complianceData?.rules ?? []).length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">
            No compliance rules configured
          </p>
        ) : (
          <div className="space-y-2">
            {(complianceData?.rules ?? []).map((r) => (
              <div
                key={r.id}
                className="flex justify-between text-sm py-1 border-b border-[var(--border-default)] last:border-0"
              >
                <span className="text-[var(--text-primary)]">{r.name}</span>
                <span
                  className={`text-xs ${
                    r.status === "passing"
                      ? "text-[var(--gain-green)]"
                      : r.status === "violated"
                        ? "text-[var(--loss-red)]"
                        : "text-[var(--text-muted)]"
                  }`}
                >
                  {r.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <KillSwitchPanel />

      {paperLive && paperLive.mode === "paper" && (
        <section className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
          <h2 className="text-sm font-medium text-[var(--accent-gold)]">
            Paper-to-Live Transition
          </h2>
          <PaperToLiveFlow />
        </section>
      )}

      <section className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
        <h2 className="text-sm font-medium text-[var(--accent-gold)]">
          Attention Report
        </h2>
        <AttentionReport />
      </section>

      <section className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
        <h2 className="text-sm font-medium text-[var(--accent-gold)]">
          Notification Preferences
        </h2>
        <NotificationPreferences />
      </section>

      <section className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
        <h2 className="text-sm font-medium text-[var(--accent-gold)]">
          Weekly Attention Summary
        </h2>
        <WeeklyAttentionSummary />
      </section>

      <NotificationPermissionRequest />
    </div>
  );
}

function SettingField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className="text-sm font-mono-nums tabular-nums text-[var(--text-primary)] mt-0.5">
        {value}
      </p>
    </div>
  );
}

function KillSwitchPanel() {
  const { data: killSwitch } = useKillSwitch();
  const clearKillSwitch = useClearKillSwitch();
  const [confirmationCode, setConfirmationCode] = useState("");
  const [stateBrief, setStateBrief] = useState("");
  const [dwellSeconds, setDwellSeconds] = useState(0);
  const [dwellActive, setDwellActive] = useState(false);
  const [step, setStep] = useState<"idle" | "confirming">("idle");
  const dwellIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const DWELL_REQUIRED_SECONDS = 5;

  useEffect(() => {
    if (dwellActive && dwellSeconds < DWELL_REQUIRED_SECONDS) {
      dwellIntervalRef.current = setInterval(() => {
        setDwellSeconds((s) => s + 1);
      }, 1000);
    } else if (
      dwellSeconds >= DWELL_REQUIRED_SECONDS &&
      dwellIntervalRef.current
    ) {
      clearInterval(dwellIntervalRef.current);
    }
    return () => {
      if (dwellIntervalRef.current) clearInterval(dwellIntervalRef.current);
    };
  }, [dwellActive, dwellSeconds]);

  const handleClearRequest = () => {
    setStep("confirming");
    setDwellActive(true);
    setDwellSeconds(0);
  };

  const handleClearConfirm = () => {
    if (dwellSeconds < DWELL_REQUIRED_SECONDS) return;
    clearKillSwitch.mutate({
      user_approved: true,
      state_brief: { cleared_by: "user", dwell_seconds: dwellSeconds },
      confirmation_code: confirmationCode,
    });
    setStep("idle");
    setDwellActive(false);
    setDwellSeconds(0);
    setConfirmationCode("");
    setStateBrief("");
  };

  const handleCancel = () => {
    setStep("idle");
    setDwellActive(false);
    setDwellSeconds(0);
    setConfirmationCode("");
    setStateBrief("");
  };

  return (
    <section className="rounded-[var(--radius)] border border-[var(--loss-red)]/30 bg-[var(--loss-red)]/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-[var(--loss-red)]">
          Kill Switch
        </h2>
        {killSwitch?.isActive && (
          <span className="flex items-center gap-1.5 text-xs text-[var(--loss-red)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--loss-red)] animate-pulse" />
            Active
          </span>
        )}
      </div>

      {!killSwitch?.isActive ? (
        <p className="text-xs text-[var(--text-muted)]">
          No kill switch currently active.
        </p>
      ) : step === "idle" ? (
        <div className="space-y-2">
          <p className="text-xs text-[var(--text-secondary)]">
            Trading is paused. To resume, you must confirm this action.
          </p>
          <button
            onClick={handleClearRequest}
            className="w-full py-2 rounded-[var(--radius)] border border-[var(--loss-red)]/50 text-[var(--loss-red)] text-sm font-medium hover:bg-[var(--loss-red)]/10 transition-colors"
          >
            Request Clear
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-[var(--text-secondary)]">
            Confirm clear. Dwell on the button for {DWELL_REQUIRED_SECONDS}s to
            confirm.
          </p>
          <input
            type="text"
            placeholder="Confirmation code (if required)"
            value={confirmationCode}
            onChange={(e) => setConfirmationCode(e.target.value)}
            className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
          />
          <textarea
            placeholder="Brief description of current state"
            value={stateBrief}
            onChange={(e) => setStateBrief(e.target.value)}
            rows={2}
            className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)] resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={handleCancel}
              className="flex-1 py-2 rounded-[var(--radius)] border border-[var(--border-default)] text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleClearConfirm}
              disabled={dwellSeconds < DWELL_REQUIRED_SECONDS}
              className={cn(
                "flex-1 py-2 rounded-[var(--radius)] text-xs font-medium transition-all",
                dwellSeconds >= DWELL_REQUIRED_SECONDS
                  ? "bg-[var(--gain-green)] text-white hover:brightness-110"
                  : "bg-[var(--bg-elevated)] text-[var(--text-muted)] cursor-not-allowed",
              )}
            >
              {dwellSeconds < DWELL_REQUIRED_SECONDS
                ? `Hold ${DWELL_REQUIRED_SECONDS - dwellSeconds}s`
                : "Clear Kill Switch"}
            </button>
          </div>
          {dwellActive && (
            <p className="text-[10px] text-center text-[var(--text-muted)]">
              Keep holding to confirm
            </p>
          )}
        </div>
      )}
    </section>
  );
}
