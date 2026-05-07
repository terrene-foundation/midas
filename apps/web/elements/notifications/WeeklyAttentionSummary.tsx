"use client";

import { useAttentionReport } from "@/lib/queries/useNotifications";
import { FatigueWarning } from "@/elements/attention/FatigueWarning";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

const TIER_LABELS: Record<string, string> = {
  calm: "Calm",
  elevated: "Elevated",
  urgent: "Urgent",
  crisis: "Crisis",
};

function Bar({
  label,
  value,
  maxValue,
}: {
  label: string;
  value: number;
  maxValue: number;
}) {
  const pct = maxValue > 0 ? Math.min((value / maxValue) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-14 text-xs text-[var(--text-muted)] shrink-0">
        {label}
      </span>
      <div className="flex-1 h-3 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
        <div
          className="h-full rounded-full bg-[var(--accent-gold)]/70 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-6 text-xs text-[var(--text-muted)] text-right shrink-0 font-mono-nums tabular-nums">
        {value}
      </span>
    </div>
  );
}

export function WeeklyAttentionSummary({ className }: { className?: string }) {
  const { data: report, isPending } = useAttentionReport();

  if (isPending) {
    return (
      <div className={cn("space-y-3", className)}>
        <Skeleton variant="rect" className="h-12" />
        <Skeleton variant="rect" className="h-24" />
      </div>
    );
  }

  const isEmpty =
    !report ||
    (report.decision_count === 0 &&
      report.notification_volume_by_tier &&
      Object.values(report.notification_volume_by_tier).every((v) => v === 0));

  const tierData = report?.notification_volume_by_tier ?? {};
  const maxTierValue = Math.max(...Object.values(tierData), 1);

  const totalSeconds = report?.decision_seconds_this_week ?? 0;
  const decisionCount = report?.decision_count ?? 0;
  const avgTime = report?.average_time_to_decide ?? 0;
  const overrideRate = report?.override_rate ?? 0;
  const fatigue = report?.fatigue_signal_present ?? false;

  return (
    <div className={cn("space-y-4", className)}>
      {/* Stat row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatBlock
          label="Decision Time"
          value={
            decisionCount === 0 ? "—" : `${Math.round(totalSeconds / 60)}m`
          }
          sub="this week"
        />
        <StatBlock
          label="Decisions"
          value={decisionCount === 0 ? "—" : String(decisionCount)}
          sub="this week"
        />
        <StatBlock
          label="Avg Time/Decide"
          value={avgTime === 0 ? "—" : `${avgTime.toFixed(1)}s`}
          sub="deliberation"
        />
        <StatBlock
          label="Override Rate"
          value={
            decisionCount === 0
              ? "—"
              : overrideRate > 0
                ? `${(overrideRate * 100).toFixed(1)}%`
                : "—"
          }
          sub="this week"
        />
      </div>

      {/* Notification volume bars */}
      {isEmpty ? (
        <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <p className="text-xs text-[var(--text-muted)]">
            No activity this week
          </p>
        </div>
      ) : (
        <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-2">
          <p className="text-xs font-medium text-[var(--text-secondary)] mb-2">
            Notification Volume by Tier
          </p>
          {Object.entries(tierData).map(([tier, count]) => (
            <Bar
              key={tier}
              label={TIER_LABELS[tier] ?? tier}
              value={count as number}
              maxValue={maxTierValue}
            />
          ))}
        </div>
      )}

      {/* Fatigue signal */}
      {fatigue && <FatigueWarning className="mt-2" />}
    </div>
  );
}

function StatBlock({
  label,
  value,
  sub,
  accent = false,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 space-y-0.5">
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p
        className={cn(
          "text-base font-semibold font-mono-nums tabular-nums",
          accent ? "text-[var(--accent-gold)]" : "text-[var(--text-primary)]",
        )}
      >
        {value}
      </p>
      <p className="text-[10px] text-[var(--text-muted)]">{sub}</p>
    </div>
  );
}
