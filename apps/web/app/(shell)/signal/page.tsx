"use client";

import { useSignals } from "@/lib/queries/useSignal";
import { Skeleton } from "@/elements/LoadingSkeleton";

export default function SignalPage() {
  const { data: signalsData, isPending } = useSignals();

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">
        Signal Feed
      </h1>

      {isPending ? (
        <div className="space-y-2">
          <Skeleton variant="card" />
          <Skeleton variant="card" />
          <Skeleton variant="card" />
        </div>
      ) : (
        <div className="space-y-2">
          {(signalsData?.signals ?? []).map((s) => (
            <div
              key={s.id}
              className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 flex items-center justify-between"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`w-2 h-2 rounded-full ${
                    s.direction === "bullish"
                      ? "bg-[var(--gain-green)]"
                      : s.direction === "bearish"
                        ? "bg-[var(--loss-red)]"
                        : "bg-[var(--accent-gold)]"
                  }`}
                />
                <div>
                  <p className="text-sm text-[var(--text-primary)]">
                    {s.instrument} &middot;{" "}
                    <span className="text-[var(--text-secondary)]">
                      {s.signal_type}
                    </span>
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {s.source} &middot; Strength:{" "}
                    {(s.strength * 100).toFixed(0)}%
                  </p>
                </div>
              </div>
              <span className="text-xs text-[var(--text-muted)]">
                {new Date(s.timestamp).toLocaleDateString()}
              </span>
            </div>
          ))}
          {!signalsData?.signals?.length && (
            <p className="text-sm text-[var(--text-muted)] text-center py-8">
              No active signals
            </p>
          )}
        </div>
      )}
    </div>
  );
}
