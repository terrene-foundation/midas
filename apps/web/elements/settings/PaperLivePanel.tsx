"use client";

import { useState } from "react";
import { usePaperLiveState } from "@/lib/queries/useSettings";
import { ReAuthModal } from "@/elements/ReAuthModal";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

const MIN_PAPER_DAYS = 14;

export function PaperLivePanel() {
  const { data: paperLive, isPending } = usePaperLiveState();

  const [showReAuth, setShowReAuth] = useState(false);
  const [paperReportAcknowledged, setPaperReportAcknowledged] = useState(false);
  const [transitionError, setTransitionError] = useState("");

  if (isPending) {
    return <Skeleton variant="rect" className="h-48" />;
  }

  if (!paperLive) {
    return (
      <p className="text-sm text-[var(--text-muted)]">
        Failed to load paper/live state
      </p>
    );
  }

  const isPaper = paperLive.mode === "paper";
  const daysElapsed = paperLive.days_in_paper ?? 0;
  const daysRemaining = Math.max(0, MIN_PAPER_DAYS - daysElapsed);
  const canGoLive = daysRemaining === 0 && paperReportAcknowledged;
  const isNewlyLive =
    paperLive.mode === "live" &&
    paperLive.live_start_date &&
    (() => {
      const start = new Date(paperLive.live_start_date!);
      const now = new Date();
      const daysSince = Math.floor(
        (now.getTime() - start.getTime()) / (1000 * 60 * 60 * 24),
      );
      return daysSince <= 7;
    })();

  // Blocking conditions for going live
  const blockingConditions = [
    {
      id: "min_days",
      label: `${MIN_PAPER_DAYS}-day minimum`,
      met: daysRemaining === 0,
      detail: `${daysElapsed} of ${MIN_PAPER_DAYS} days completed`,
    },
    {
      id: "report_acknowledged",
      label: "Paper report viewed & acknowledged",
      met: paperReportAcknowledged,
      detail: paperReportAcknowledged
        ? "Acknowledged"
        : "View paper trading report to proceed",
    },
  ];

  const handleGoLiveRequest = () => {
    setShowReAuth(true);
  };

  const handleReAuthResult = (success: boolean) => {
    setShowReAuth(false);
    if (success) {
      // Actually trigger the transition
      transitionToLive();
    }
  };

  const transitionToLive = async () => {
    try {
      const { api } = await import("@/lib/api-client");
      await api.post("/settings/paper-live/transition", {});
      setTransitionError("");
      // Refresh will happen via query invalidation
      window.location.reload();
    } catch (err) {
      setTransitionError(String(err));
    }
  };

  return (
    <div className="space-y-4">
      {isNewlyLive && (
        <div className="rounded border border-[var(--accent-gold)] bg-[var(--accent-gold)]/10 p-3">
          <p className="text-sm text-[var(--accent-gold)] font-medium">
            First 7 days at L1
          </p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            Operating at Level 1 during initial live transition period.
          </p>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Trading Mode
          </p>
          <p
            className={cn(
              "text-sm font-semibold",
              isPaper
                ? "text-[var(--accent-gold)]"
                : "text-[var(--gain-green)]",
            )}
          >
            {isPaper ? "Paper Trading" : "Live Trading"}
          </p>
        </div>
        <div
          className={cn(
            "px-3 py-1 rounded-full text-xs font-medium",
            isPaper
              ? "bg-[var(--accent-gold)]/20 text-[var(--accent-gold)]"
              : "bg-[var(--gain-green)]/20 text-[var(--gain-green)]",
          )}
        >
          {isPaper ? "PAPER" : "LIVE"}
        </div>
      </div>

      {isPaper && (
        <div className="space-y-3">
          <div>
            <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
              <span>Paper Trading Progress</span>
              <span>
                {daysElapsed} / {MIN_PAPER_DAYS} days
              </span>
            </div>
            <div className="h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
              <div
                className="h-full rounded-full bg-[var(--accent-gold)] transition-all"
                style={{
                  width: `${Math.min(100, (daysElapsed / MIN_PAPER_DAYS) * 100)}%`,
                }}
              />
            </div>
            {daysRemaining > 0 && (
              <p className="text-xs text-[var(--text-muted)] mt-1">
                {daysRemaining} days remaining before eligible for live
                transition
              </p>
            )}
          </div>

          <div className="rounded border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 space-y-2">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
              Live Transition Requirements
            </p>
            {blockingConditions.map((condition) => (
              <div key={condition.id} className="flex items-start gap-2">
                <div
                  className={cn(
                    "w-4 h-4 rounded flex items-center justify-center mt-0.5",
                    condition.met
                      ? "bg-[var(--gain-green)] text-white"
                      : "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
                  )}
                >
                  {condition.met ? "✓" : "○"}
                </div>
                <div className="flex-1">
                  <p
                    className={cn(
                      "text-sm",
                      condition.met
                        ? "text-[var(--text-primary)]"
                        : "text-[var(--text-secondary)]",
                    )}
                  >
                    {condition.label}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {condition.detail}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {!paperReportAcknowledged && (
            <button
              onClick={() => setPaperReportAcknowledged(true)}
              className="w-full px-4 py-2 rounded text-sm border border-[var(--border-default)] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
            >
              View & Acknowledge Paper Report
            </button>
          )}

          {paperReportAcknowledged && (
            <div className="flex items-center gap-2 text-sm text-[var(--gain-green)]">
              <span>✓</span>
              <span>Paper report acknowledged</span>
            </div>
          )}

          {transitionError && (
            <p className="text-xs text-[var(--loss-red)]">{transitionError}</p>
          )}

          <button
            onClick={handleGoLiveRequest}
            disabled={!canGoLive || showReAuth}
            className={cn(
              "w-full px-4 py-2 rounded text-sm font-medium transition-colors",
              canGoLive
                ? "bg-[var(--gain-green)] text-white hover:opacity-90"
                : "bg-[var(--bg-elevated)] text-[var(--text-muted)] cursor-not-allowed",
            )}
          >
            {!canGoLive ? "Conditions Not Met" : "Go Live"}
          </button>
        </div>
      )}

      {!isPaper && paperLive.live_start_date && (
        <div className="text-xs text-[var(--text-muted)]">
          Live since {new Date(paperLive.live_start_date).toLocaleDateString()}
        </div>
      )}

      <ReAuthModal
        open={showReAuth}
        onResult={handleReAuthResult}
        reason="Transitioning to live trading requires re-authentication"
      />
    </div>
  );
}
