"use client";

import { useAutonomyState, useSetAutonomy } from "@/lib/queries/useSettings";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

export function UpgradeProposalCard() {
  const { data: autonomy, isPending } = useAutonomyState();
  const setAutonomy = useSetAutonomy();

  if (isPending) {
    return <Skeleton variant="rect" className="h-64" />;
  }

  if (!autonomy) {
    return null;
  }

  // Show upgrade proposal only if there's a pending proposal
  if (!autonomy.pending_upgrade) {
    return (
      <div className="rounded border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <p className="text-sm text-[var(--text-muted)]">
          No pending upgrade proposal
        </p>
      </div>
    );
  }

  const proposal = autonomy.pending_upgrade;
  const newLevel = autonomy.level + 1;

  return (
    <div className="space-y-4 rounded border border-[var(--accent-gold)] bg-[var(--bg-surface)] p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--accent-gold)]">
          Upgrade Proposal
        </h3>
        <span className="text-xs text-[var(--text-muted)]">
          L{autonomy.level} → L{newLevel}
        </span>
      </div>

      <div className="space-y-3">
        <div>
          <p className="text-xs text-[var(--text-muted)] mb-1">
            Operating History
          </p>
          <div className="grid grid-cols-3 gap-2">
            <StatBox
              label="Days"
              value={proposal.operating_history.days_at_level}
            />
            <StatBox
              label="Decisions"
              value={proposal.operating_history.total_decisions}
            />
            <StatBox
              label="Override Rate"
              value={`${(proposal.operating_history.override_rate * 100).toFixed(1)}%`}
            />
          </div>
        </div>

        <div>
          <p className="text-xs text-[var(--text-muted)] mb-1">
            Brinson Attribution
          </p>
          <div className="rounded bg-[var(--bg-elevated)] p-2 text-xs font-mono">
            {Object.entries(proposal.brinson_snapshot).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-[var(--text-secondary)]">{k}</span>
                <span
                  className={cn(
                    (v as number) >= 0
                      ? "text-[var(--gain-green)]"
                      : "text-[var(--loss-red)]",
                  )}
                >
                  {(v as number).toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs text-[var(--text-muted)] mb-1">
            Calibration Snapshot
          </p>
          <div className="rounded bg-[var(--bg-elevated)] p-2 text-xs space-y-1">
            {Object.entries(proposal.calibration_snapshot).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-[var(--text-secondary)]">{k}</span>
                <span className="text-[var(--text-primary)]">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs text-[var(--text-muted)] mb-1">Override Log</p>
          <div className="max-h-24 overflow-y-auto rounded bg-[var(--bg-elevated)] p-2 text-xs space-y-1">
            {proposal.override_log.length === 0 ? (
              <p className="text-[var(--text-muted)]">No overrides</p>
            ) : (
              proposal.override_log.map(
                (
                  entry: {
                    decision_id: string;
                    reason: string;
                    timestamp: string;
                  },
                  i: number,
                ) => (
                  <div key={i} className="text-[var(--text-secondary)]">
                    <span className="text-[var(--text-muted)]">
                      #{entry.decision_id.slice(0, 8)}
                    </span>
                    <span className="ml-2">{entry.reason}</span>
                  </div>
                ),
              )
            )}
          </div>
        </div>

        <div>
          <p className="text-xs text-[var(--text-muted)] mb-1">
            What Changes at L{newLevel}
          </p>
          <ul className="text-xs text-[var(--text-secondary)] space-y-1">
            {proposal.changes_at_new_level.map((change: string, i: number) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-[var(--accent-gold)]">+</span>
                {change}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="flex gap-3 pt-4 border-t border-[var(--border-default)]">
        <button
          onClick={() => setAutonomy.mutate(newLevel)}
          disabled={setAutonomy.isPending}
          className="flex-1 px-4 py-2 rounded text-sm font-medium bg-[var(--gain-green)] text-white disabled:opacity-50 transition-colors"
        >
          Approve
        </button>
        <button
          onClick={() => setAutonomy.mutate(autonomy.level)}
          disabled={setAutonomy.isPending}
          className="flex-1 px-4 py-2 rounded text-sm font-medium border border-[var(--loss-red)] text-[var(--loss-red)] hover:bg-[var(--loss-red)] hover:text-white transition-colors"
        >
          Decline
        </button>
      </div>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded bg-[var(--bg-elevated)] p-2 text-center">
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className="text-sm font-mono font-medium text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
