"use client";

import { useState } from "react";
import { usePaperLiveState } from "@/lib/queries/useSettings";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { ReAuthModal } from "@/elements/ReAuthModal";
import { cn } from "@/elements/ui/utils";
import { Skeleton } from "@/elements/LoadingSkeleton";

interface PaperToLiveFlowProps {
  className?: string;
}

type Step = "check" | "blocked" | "eligible" | "review" | "confirm";

interface BlockingCondition {
  id: string;
  label: string;
  explanation: string;
  met: boolean;
}

type PaperState = NonNullable<ReturnType<typeof usePaperLiveState>["data"]>;

function CheckBlockingConditions({
  paperState,
  onBlocked,
  onEligible,
}: {
  paperState: PaperState;
  onBlocked: (conditions: BlockingCondition[]) => void;
  onEligible: () => void;
}) {
  const MINIMUM_PAPER_DAYS = 14;

  const { data: healthData } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get("/health"),
  });

  const subsystemsOk = healthData?.status === "healthy" || healthData?.dependencies?.every(
    (d: { status: string }) => d.status === "healthy"
  ) ?? false;

  const { data: anomaliesData } = useQuery({
    queryKey: ["anomalies"],
    queryFn: () => api.get("/scheduler/jobs"),
  });

  const noAnomalies = !(anomaliesData?.jobs?.some(
    (j: { status: string }) => j.status === "failed"
  ) ?? false);

  const conditions: BlockingCondition[] = [
    {
      id: "min_days",
      label: `${MINIMUM_PAPER_DAYS}-day minimum`,
      explanation: `Paper trading must run for at least ${MINIMUM_PAPER_DAYS} days before transitioning to live. This enforces the learning period.`,
      met: paperState.days_in_paper >= MINIMUM_PAPER_DAYS,
    },
    {
      id: "no_subsystem_failures",
      label: "No subsystem failures",
      explanation:
        "All subsystems (data feeds, order execution, risk controls) must be operating normally.",
      met: subsystemsOk,
    },
    {
      id: "no_critical_anomalies",
      label: "No critical anomalies",
      explanation:
        "No critical anomalies detected in the paper trading period that would indicate model instability.",
      met: noAnomalies,
    },
  ];

  const unmet = conditions.filter((c) => !c.met);

  if (unmet.length > 0) {
    onBlocked(conditions);
  } else {
    onEligible();
  }

  return null;
}

function ReviewSurface({ onAcknowledge }: { onAcknowledge: () => void }) {
  const [scrolledToBottom, setScrolledToBottom] = useState(false);

  const { data: reportData, isPending: reportLoading } = useQuery({
    queryKey: ["paper-trading-report"],
    queryFn: () => api.get("/settings/paper-live/report"),
  });

  const reportSections = reportData?.sections ?? [];
  const overallStatus = reportData?.overall_status ?? "pending";

  return (
    <div className="space-y-4">
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[var(--accent-gold)]">
            Paper Trading Report
          </h3>
          {overallStatus && (
            <span className={cn(
              "text-xs px-2 py-0.5 rounded",
              overallStatus === "pass"
                ? "bg-[var(--gain-green)]/10 text-[var(--gain-green)]"
                : "bg-[var(--accent-gold)]/10 text-[var(--accent-gold)]"
            )}>
              {overallStatus}
            </span>
          )}
        </div>
        <div
          className="max-h-64 overflow-y-auto text-sm text-[var(--text-secondary)] space-y-2 pr-2"
          onScroll={(e) => {
            const el = e.currentTarget;
            const atBottom =
              el.scrollHeight - el.scrollTop - el.clientHeight < 8;
            if (atBottom) setScrolledToBottom(true);
          }}
        >
          {reportLoading ? (
            <div className="space-y-2">
              <Skeleton variant="text" className="h-4 w-3/4" />
              <Skeleton variant="text" className="h-4 w-full" />
              <Skeleton variant="text" className="h-4 w-5/6" />
            </div>
          ) : reportSections.length > 0 ? (
            reportSections.map((section: { title: string; content: string; status?: string }, idx: number) => (
              <div key={idx} className="space-y-1">
                {section.title && (
                  <p className="font-medium text-[var(--text-primary)]">
                    {section.title}
                    {section.status && (
                      <span className={cn(
                        "ml-2 text-xs px-1.5 py-0.5 rounded",
                        section.status === "pass"
                          ? "bg-[var(--gain-green)]/10 text-[var(--gain-green)]"
                          : section.status === "fail"
                            ? "bg-[var(--loss-red)]/10 text-[var(--loss-red)]"
                            : "bg-[var(--accent-gold)]/10 text-[var(--accent-gold)]"
                      )}>
                        {section.status}
                      </span>
                    )}
                  </p>
                )}
                <p>{section.content}</p>
              </div>
            ))
          ) : (
            <div className="text-center py-6 text-[var(--text-muted)]">
              No report data available. Ensure paper trading has been running.
            </div>
          )}
        </div>
      </div>

      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={scrolledToBottom}
          onChange={() => {}}
          disabled
          className="accent-[var(--accent-gold)]"
        />
        <span
          className={cn(
            "text-sm",
            scrolledToBottom
              ? "text-[var(--text-primary)]"
              : "text-[var(--text-muted)]",
          )}
        >
          I have reviewed this report
        </span>
      </label>

      <button
        onClick={onAcknowledge}
        disabled={!scrolledToBottom}
        className="w-full py-3 rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-base)] font-medium text-sm disabled:opacity-40 hover:brightness-110 transition-all"
      >
        Continue
      </button>
    </div>
  );
}

function ConfirmationStep({
  paperState,
  onBack,
  onConfirm,
}: {
  paperState: PaperState;
  onBack: () => void;
  onConfirm: () => void;
}) {
  const [reAuthOpen, setReAuthOpen] = useState(false);

  const handleConfirmPress = () => {
    setReAuthOpen(true);
  };

  const handleReAuthResult = (ok: boolean) => {
    setReAuthOpen(false);
    if (ok) onConfirm();
  };

  return (
    <>
      <div className="space-y-4">
        <div className="rounded-[var(--radius)] border border-[var(--accent-gold)]/30 bg-[var(--accent-gold)]/5 px-4 py-3">
          <p className="text-sm font-semibold text-[var(--accent-gold)]">
            You are transitioning to live trading
          </p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            First 7 days will require approval for every decision.
          </p>
        </div>

        <div className="space-y-2 text-sm text-[var(--text-secondary)]">
          <p>
            After {paperState.days_in_paper} days of paper trading, you are
            ready to go live. From this point:
          </p>
          <ul className="list-disc list-inside space-y-1">
            <li>Orders will execute with real capital</li>
            <li>
              The first 7 calendar days require manual approval per decision
            </li>
            <li>Full autonomy unlocks after the 7-day review period</li>
          </ul>
        </div>

        <div className="flex gap-3">
          <button
            onClick={onBack}
            className="flex-1 py-2.5 rounded-[var(--radius)] border border-[var(--border-default)] text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors"
          >
            Back
          </button>
          <button
            onClick={handleConfirmPress}
            className="flex-1 py-2.5 rounded-[var(--radius)] bg-[var(--gain-green)] text-white text-sm font-medium hover:brightness-110 transition-all"
          >
            Go Live
          </button>
        </div>
      </div>

      <ReAuthModal
        open={reAuthOpen}
        reason="Transitioning to live trading requires confirmation"
        onResult={handleReAuthResult}
      />
    </>
  );
}

export function PaperToLiveFlow({ className }: PaperToLiveFlowProps) {
  const { data: paperState, isPending } = usePaperLiveState();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("check");
  const [blockingConditions, setBlockingConditions] = useState<
    BlockingCondition[] | null
  >(null);
  const transitionToLive = useMutation({
    mutationFn: () => api.post("/settings/paper-live/transition"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["paper-live"] });
      setStep("check");
    },
  });

  const handleBlocked = (conditions: BlockingCondition[]) => {
    setBlockingConditions(conditions);
    setStep("blocked");
  };

  const handleEligible = () => {
    setStep("eligible");
  };

  const handleAcknowledge = () => {
    setStep("review");
  };

  const handleReviewContinue = () => {
    setStep("confirm");
  };

  const handleGoLive = () => {
    transitionToLive.mutate();
  };

  if (isPending) {
    return (
      <div className={cn("space-y-2", className)}>
        <Skeleton variant="rect" className="h-32" />
      </div>
    );
  }

  if (!paperState || paperState.mode === "live") {
    return null;
  }

  // Step 1: Check blocking conditions
  if (step === "check") {
    return (
      <div className={className}>
        <CheckBlockingConditions
          paperState={paperState}
          onBlocked={handleBlocked}
          onEligible={handleEligible}
        />
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      {step === "blocked" && blockingConditions && (
        <div className="space-y-3">
          <div className="rounded-[var(--radius)] border border-[var(--loss-red)]/30 bg-[var(--loss-red)]/5 px-4 py-3">
            <p className="text-sm font-semibold text-[var(--loss-red)]">
              Cannot transition yet
            </p>
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              The following conditions must be met before going live:
            </p>
          </div>
          <div className="space-y-2">
            {blockingConditions.map((c) => (
              <div
                key={c.id}
                className="flex items-start gap-2 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3"
              >
                <div
                  className={cn(
                    "mt-0.5 w-2 h-2 rounded-full flex-shrink-0",
                    c.met ? "bg-[var(--gain-green)]" : "bg-[var(--loss-red)]",
                  )}
                />
                <div className="space-y-0.5">
                  <p
                    className={cn(
                      "text-sm font-medium",
                      c.met
                        ? "text-[var(--gain-green)]"
                        : "text-[var(--text-primary)]",
                    )}
                  >
                    {c.label}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {c.explanation}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {step === "eligible" && (
        <div className="rounded-[var(--radius)] border border-[var(--gain-green)]/30 bg-[var(--gain-green)]/5 px-4 py-3">
          <p className="text-sm font-semibold text-[var(--gain-green)]">
            Eligible to go live
          </p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            All requirements met. Review your paper trading report to proceed.
          </p>
          <button
            onClick={handleAcknowledge}
            className="mt-3 w-full py-2 rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-base)] text-sm font-medium hover:brightness-110 transition-all"
          >
            View Paper Trading Report
          </button>
        </div>
      )}

      {step === "review" && (
        <ReviewSurface onAcknowledge={handleReviewContinue} />
      )}

      {step === "confirm" && (
        <ConfirmationStep
          paperState={paperState}
          onBack={() => setStep("review")}
          onConfirm={handleGoLive}
        />
      )}
    </div>
  );
}
