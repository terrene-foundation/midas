"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useOnboardingStatus } from "@/lib/queries/useOnboarding";
import type { OnboardingStep } from "@/lib/types";
import { StepBrokerage } from "./StepBrokerage";
import { StepRiskProfile } from "./StepRiskProfile";
import { StepPaperTrading } from "./StepPaperTrading";
import { StepReview } from "./StepReview";
import { NotificationPermissionRequest } from "@/elements/notifications";
import { cn } from "@/elements/ui/utils";
import { Skeleton } from "@/elements/LoadingSkeleton";

const STEPS: { key: OnboardingStep; label: string; n: number }[] = [
  { key: "connect", label: "Connect Brokerage", n: 1 },
  { key: "risk", label: "Risk Profile", n: 2 },
  { key: "universe", label: "Universe Constraints", n: 3 },
  { key: "activate", label: "Activate", n: 4 },
];

export function OnboardingWizard() {
  const router = useRouter();
  const { data: status, isPending } = useOnboardingStatus();

  const initialStep: OnboardingStep =
    status && status.step !== "done" ? status.step : "connect";

  const [step, setStep] = useState<OnboardingStep>(initialStep);
  const [error, setError] = useState("");

  // Sync step from server state when it arrives (resume on refresh)
  if (
    status &&
    step === "connect" &&
    status.step !== "connect" &&
    status.step !== "done"
  ) {
    setStep(status.step);
  }

  const stepIndex = STEPS.findIndex((s) => s.key === step);
  const progress =
    step === "done" ? 100 : Math.round((stepIndex / STEPS.length) * 100);

  function handleComplete() {
    const nextStep = STEPS[stepIndex + 1]?.key;
    if (nextStep) {
      setStep(nextStep);
    } else {
      setStep("done");
    }
  }

  function handleError(message: string) {
    setError(message);
  }

  function handleDone() {
    router.push("/pulse");
  }

  if (isPending) {
    return (
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <Skeleton className="h-6 w-48" />
        <Skeleton variant="rect" className="h-2 w-full" />
        <Skeleton variant="card" className="h-64" />
      </div>
    );
  }

  if (status?.activated) {
    router.replace("/pulse");
    return null;
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">
        Set Up Your Investment Assistant
      </h1>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="h-2 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--accent-gold)] transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-[var(--text-muted)]">
          {STEPS.map((s) => {
            const currentIndex = STEPS.findIndex((x) => x.key === step);
            const isComplete =
              currentIndex > STEPS.findIndex((x) => x.key === s.key);
            const isCurrent = s.key === step;
            return (
              <span
                key={s.key}
                className={cn(
                  isComplete && "text-[var(--text-primary)] font-medium",
                  isCurrent && "text-[var(--accent-gold)] font-medium",
                )}
              >
                {s.n}. {s.label}
              </span>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="rounded-[var(--radius)] border border-[var(--loss-red)]/30 bg-[var(--loss-red)]/5 p-3 text-sm text-[var(--loss-red)]">
          {error}
        </div>
      )}

      {/* Step content */}
      {step === "connect" && (
        <StepBrokerage onComplete={handleComplete} onError={handleError} />
      )}
      {step === "risk" && (
        <StepRiskProfile onComplete={handleComplete} onError={handleError} />
      )}
      {step === "universe" && (
        <StepPaperTrading onComplete={handleComplete} onError={handleError} />
      )}
      {step === "activate" && (
        <StepReview
          onComplete={handleComplete}
          onDone={handleDone}
          onError={handleError}
        />
      )}
      {step === "done" && (
        <div className="rounded-[var(--radius)] border border-[var(--gain-green)]/30 bg-[var(--gain-green)]/5 p-6 text-center space-y-3">
          <h2 className="text-base font-medium text-[var(--gain-green)]">
            Setup Complete
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            Your investment assistant is now active in paper trading mode. Visit
            the Pulse dashboard to monitor its decisions.
          </p>
          <NotificationPermissionRequest className="mt-4" />
          <button
            onClick={handleDone}
            className="inline-block rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-primary)] px-6 py-2 text-sm font-medium hover:opacity-90 transition-opacity"
          >
            Go to Dashboard
          </button>
        </div>
      )}
    </div>
  );
}
