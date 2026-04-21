"use client";

import { useAutonomyState } from "@/lib/queries/useSettings";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

export function AutonomyViewer() {
  const { data: autonomy, isPending } = useAutonomyState();

  if (isPending) {
    return <Skeleton variant="rect" className="h-40" />;
  }

  if (!autonomy) {
    return (
      <p className="text-sm text-[var(--text-muted)]">
        Failed to load autonomy state
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div className="flex items-center justify-center w-16 h-16 rounded-full bg-[var(--bg-elevated)] border border-[var(--border-default)]">
          <span className="text-2xl font-bold text-[var(--accent-gold)]">
            L{autonomy.level}
          </span>
        </div>
        <div>
          <p className="text-lg font-semibold text-[var(--text-primary)]">
            {autonomy.level_name}
          </p>
          <p className="text-sm text-[var(--text-secondary)]">
            {autonomy.can_auto_approve
              ? "Auto-approve enabled"
              : "Manual approval required"}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 pt-4 border-t border-[var(--border-default)]">
        <div className="space-y-1">
          <p className="text-xs text-[var(--text-muted)]">Requires Re-auth</p>
          <p
            className={cn(
              "text-sm font-medium",
              autonomy.requires_reauth
                ? "text-[var(--loss-red)]"
                : "text-[var(--gain-green)]",
            )}
          >
            {autonomy.requires_reauth ? "Yes" : "No"}
          </p>
        </div>
        <div className="space-y-1">
          <p className="text-xs text-[var(--text-muted)]">Upgrade Eligible</p>
          <p
            className={cn(
              "text-sm font-medium",
              autonomy.level < 5
                ? "text-[var(--gain-green)]"
                : "text-[var(--text-muted)]",
            )}
          >
            {autonomy.level < 5 ? "Yes" : "Max Level"}
          </p>
        </div>
      </div>

      <div className="space-y-2 pt-4 border-t border-[var(--border-default)]">
        <p className="text-xs text-[var(--text-muted)]">Level Change History</p>
        {(autonomy.level_history ?? []).length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">
            No level changes recorded
          </p>
        ) : (
          <div className="space-y-2">
            {(autonomy.level_history ?? []).map(
              (
                entry: {
                  from_level: number;
                  to_level: number;
                  changed_at: string;
                },
                i: number,
              ) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm py-2 border-b border-[var(--border-default)] last:border-0"
                >
                  <span className="text-[var(--text-secondary)]">
                    L{entry.from_level} → L{entry.to_level}
                  </span>
                  <span className="text-xs text-[var(--text-muted)]">
                    {new Date(entry.changed_at).toLocaleDateString()}
                  </span>
                </div>
              ),
            )}
          </div>
        )}
      </div>
    </div>
  );
}
