"use client";

import {
  useEnvelopeConfig,
  useAutonomyState,
  usePaperLiveState,
  useUpdateEnvelope,
} from "@/lib/queries/useSettings";
import { useComplianceRules } from "@/lib/queries/useCompliance";
import { Skeleton } from "@/elements/LoadingSkeleton";

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
