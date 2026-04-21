"use client";

import { useState } from "react";
import { useApproveDecision } from "@/lib/queries/useDecisions";
import { ReAuthModal } from "@/elements/ReAuthModal";
import { QuoteMovedDialog } from "./QuoteMovedDialog";
import type { Band } from "@/stores/regime-store";
import { cn } from "@/elements/ui/utils";

interface ApprovalFlowProps {
  decisionId: string;
  band: Band;
  isUrgentOrCrisis: boolean;
  needsReAuth: boolean;
  currentPrice?: number;
  briefPrice?: number;
  onApproved: () => void;
  onCancel: () => void;
  className?: string;
}

type ApprovalStep = "idle" | "reauth" | "quote_moved" | "submitting" | "done";

/**
 * Multi-step approval flow:
 * 1. User taps Approve
 * 2. If Urgent/Crisis OR above dollar threshold → show ReAuthModal first
 * 3. After re-auth → check if quote moved (per 10 S6.4)
 * 4. Submit approval
 */
export function ApprovalFlow({
  decisionId,
  band,
  isUrgentOrCrisis,
  needsReAuth,
  currentPrice,
  briefPrice,
  onApproved,
  onCancel,
  className,
}: ApprovalFlowProps) {
  const [step, setStep] = useState<ApprovalStep>("idle");
  const [reAuthPassed, setReAuthPassed] = useState(false);

  const approve = useApproveDecision();

  const handleApproveClick = () => {
    if (isUrgentOrCrisis || needsReAuth) {
      setStep("reauth");
    } else {
      submitApproval();
    }
  };

  const handleReAuthResult = (success: boolean) => {
    if (success) {
      setReAuthPassed(true);
      // Check quote moved after re-auth per spec 10 S6.4
      if (currentPrice && briefPrice && briefPrice !== currentPrice) {
        const priceChangePct = ((currentPrice - briefPrice) / briefPrice) * 100;
        const absChange = Math.abs(priceChangePct);

        const thresholds = {
          calm: 0.5,
          elevated: 0.3,
          urgent: 0.2,
          crisis: 0.1,
        };

        if (absChange >= thresholds[band]) {
          setStep("quote_moved");
          return;
        }
      }
      submitApproval();
    } else {
      setStep("idle");
    }
  };

  const submitApproval = () => {
    setStep("submitting");
    approve.mutate(decisionId, {
      onSuccess: () => {
        setStep("done");
        onApproved();
      },
      onError: () => {
        setStep("idle");
      },
    });
  };

  const handleProceedAtCurrent = () => {
    submitApproval();
  };

  const handleSetLimit = () => {
    // For now, just cancel - limit order would be a separate flow
    onCancel();
  };

  const handleQuoteMovedCancel = () => {
    setStep("idle");
    onCancel();
  };

  return (
    <>
      <div className={cn("space-y-3", className)}>
        {step === "idle" && (
          <button
            onClick={handleApproveClick}
            className="w-full py-2.5 rounded-[var(--radius)] bg-[var(--gain-green)] text-white text-sm font-medium hover:brightness-110 transition-all"
          >
            Approve
          </button>
        )}

        {step === "submitting" && (
          <button
            disabled
            className="w-full py-2.5 rounded-[var(--radius)] bg-[var(--gain-green)]/50 text-white text-sm font-medium"
          >
            Submitting...
          </button>
        )}

        {step === "done" && (
          <div className="text-center py-2">
            <div className="text-[var(--gain-green)] text-sm font-medium">
              ✓ Approved
            </div>
          </div>
        )}
      </div>

      <ReAuthModal
        open={step === "reauth"}
        reason={`Approving ${band} decision requires confirmation`}
        onResult={handleReAuthResult}
      />

      <QuoteMovedDialog
        open={step === "quote_moved"}
        priceChangePct={
          currentPrice && briefPrice
            ? ((currentPrice - briefPrice) / briefPrice) * 100
            : 0
        }
        band={band}
        onProceedAtCurrent={handleProceedAtCurrent}
        onSetLimit={handleSetLimit}
        onCancel={handleQuoteMovedCancel}
      />
    </>
  );
}
