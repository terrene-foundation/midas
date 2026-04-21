"use client";

import { useState } from "react";
import {
  useKillSwitch,
  useActivateKillSwitch,
  useClearKillSwitch,
} from "@/lib/queries/useCompliance";
import { ReAuthModal } from "@/elements/ReAuthModal";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

export function KillSwitchPanel() {
  const { data: killSwitch, isPending } = useKillSwitch();
  const activateKillSwitch = useActivateKillSwitch();
  const clearKillSwitch = useClearKillSwitch();

  const [showReAuth, setShowReAuth] = useState(false);
  const [showStateBrief, setShowStateBrief] = useState(false);
  const [dwelling, setDwelling] = useState(false);
  const [dwellingSeconds, setDwellingSeconds] = useState(60);
  const [clearError, setClearError] = useState("");

  if (isPending) {
    return <Skeleton variant="rect" className="h-40" />;
  }

  if (!killSwitch) {
    return (
      <p className="text-sm text-[var(--text-muted)]">
        Failed to load kill switch state
      </p>
    );
  }

  const handleActivate = () => {
    activateKillSwitch.mutate("Manual activation by operator", {
      onSuccess: () => {},
    });
  };

  const handleClearRequest = () => {
    setShowReAuth(true);
  };

  const handleReAuthResult = (success: boolean) => {
    setShowReAuth(false);
    if (success) {
      setShowStateBrief(true);
    }
  };

  const handleStateBriefAcknowledge = () => {
    setShowStateBrief(false);
    setDwelling(true);
    setDwellingSeconds(60);

    const interval = setInterval(() => {
      setDwellingSeconds((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          setDwelling(false);
          // After dwell timer completes, call clear
          clearKillSwitch.mutate(
            {
              user_approved: true,
              state_brief: killSwitch.state_brief ?? {},
              confirmation_code: killSwitch.confirmation_code ?? "",
            },
            {
              onSuccess: () => setClearError(""),
              onError: (err) => setClearError(String(err)),
            },
          );
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Kill Switch
          </p>
          <p
            className={cn(
              "text-sm",
              killSwitch.isActive
                ? "text-[var(--loss-red)]"
                : "text-[var(--gain-green)]",
            )}
          >
            {killSwitch.isActive ? "Active" : "Cleared"}
          </p>
        </div>
        <div
          className={cn(
            "w-3 h-3 rounded-full",
            killSwitch.isActive
              ? "bg-[var(--loss-red)] animate-pulse"
              : "bg-[var(--gain-green)]",
          )}
        />
      </div>

      {killSwitch.isActive && killSwitch.reason && (
        <div className="rounded bg-[var(--bg-elevated)] p-3">
          <p className="text-xs text-[var(--text-muted)]">Reason</p>
          <p className="text-sm text-[var(--text-primary)]">
            {killSwitch.reason}
          </p>
        </div>
      )}

      {killSwitch.isActive && killSwitch.activated_at && (
        <div className="text-xs text-[var(--text-muted)]">
          Activated {new Date(killSwitch.activated_at).toLocaleString()}
        </div>
      )}

      {clearError && (
        <p className="text-xs text-[var(--loss-red)]">{clearError}</p>
      )}

      <div className="flex gap-3 pt-4 border-t border-[var(--border-default)]">
        {killSwitch.isActive ? (
          <>
            <button
              onClick={handleClearRequest}
              disabled={clearKillSwitch.isPending}
              className={cn(
                "px-4 py-2 rounded text-sm font-medium transition-colors",
                "border border-[var(--accent-gold)] text-[var(--accent-gold)]",
                "hover:bg-[var(--accent-gold)] hover:text-[var(--bg-base)]",
                "disabled:opacity-50",
              )}
            >
              Clear Kill Switch
            </button>
          </>
        ) : (
          <button
            onClick={handleActivate}
            disabled={activateKillSwitch.isPending}
            className={cn(
              "px-4 py-2 rounded text-sm font-medium transition-colors",
              "bg-[var(--loss-red)] text-white",
              "hover:opacity-90",
              "disabled:opacity-50",
            )}
          >
            {activateKillSwitch.isPending
              ? "Activating..."
              : "Activate Kill Switch"}
          </button>
        )}
      </div>

      {dwelling && (
        <div className="rounded border border-[var(--accent-gold)] bg-[var(--bg-surface)] p-4 text-center">
          <p className="text-sm text-[var(--text-primary)] mb-2">
            Dwelling before clear
          </p>
          <p className="text-2xl font-mono font-bold text-[var(--accent-gold)]">
            {dwellingSeconds}s
          </p>
        </div>
      )}

      <ReAuthModal
        open={showReAuth}
        onResult={handleReAuthResult}
        reason="Clearing the kill switch requires re-authentication"
      />

      {showStateBrief && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              State of World Brief
            </h2>
            <div className="rounded bg-[var(--bg-elevated)] p-4 text-sm text-[var(--text-secondary)] max-h-60 overflow-y-auto">
              {killSwitch.state_brief ? (
                <pre className="whitespace-pre-wrap">
                  {JSON.stringify(killSwitch.state_brief, null, 2)}
                </pre>
              ) : (
                <p>No state brief available</p>
              )}
            </div>
            <p className="text-xs text-[var(--text-muted)]">
              Clearing the kill switch will revert to L1 regardless of prior
              level.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowStateBrief(false)}
                className="px-4 py-2 rounded text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleStateBriefAcknowledge}
                className="px-4 py-2 rounded text-sm font-medium bg-[var(--accent-gold)] text-[var(--bg-base)] transition-colors"
              >
                Acknowledge & Continue
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
