"use client";

import { useEffect, useRef, useState } from "react";
import { useRegimeStore } from "@/stores/regime-store";
import { cn } from "@/elements/ui/utils";

const BAND_COLORS: Record<string, string> = {
  calm: "var(--regime-calm)",
  elevated: "var(--regime-elevated)",
  urgent: "var(--regime-urgent)",
  crisis: "var(--regime-crisis)",
};

const BAND_LABELS: Record<string, string> = {
  calm: "Calm",
  elevated: "Elevated",
  urgent: "Urgent",
  crisis: "Crisis",
};

const BAND_DESCRIPTIONS: Record<string, string> = {
  calm: "Normal market conditions — routine operations",
  elevated: "Rising volatility — caution advised",
  urgent: "High risk regime — active monitoring required",
  crisis: "Critical regime — trading halted pending approval",
};

const DEBOUNCE_MS = 500;
const AUTO_DISMISS_MS = 5_000;

export function RegimeChangeToast() {
  const band = useRegimeStore((s) => s.band);
  const prevBandRef = useRef<string | null>(null);
  const [visible, setVisible] = useState(false);
  const [currentBand, setCurrentBand] = useState<string>(band);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const prev = prevBandRef.current;

    // Initial load: suppress calm toast (no regime change to announce), but
    // still show non-calm regimes (crisis/elevated/urgent) immediately
    if (prev === null) {
      prevBandRef.current = band;
      if (band === "calm") return;
      setCurrentBand(band);
      setVisible(true);
      if (band !== "crisis") {
        dismissTimer.current = setTimeout(
          () => setVisible(false),
          AUTO_DISMISS_MS,
        );
      }
      return;
    }

    if (prev === band) return;

    // Suppress calm-to-calm
    if (prev === "calm" && band === "calm") return;

    // Debounce rapid transitions
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      setCurrentBand(band);
      setVisible(true);
      prevBandRef.current = band;

      // Cancel any pending dismiss
      if (dismissTimer.current) clearTimeout(dismissTimer.current);

      // Auto-dismiss after 5s (except crisis requires manual dismiss)
      if (band !== "crisis") {
        dismissTimer.current = setTimeout(() => {
          setVisible(false);
        }, AUTO_DISMISS_MS);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [band]);

  const dismiss = () => {
    if (dismissTimer.current) clearTimeout(dismissTimer.current);
    setVisible(false);
  };

  if (!visible) return null;

  const isCrisis = currentBand === "crisis";

  return (
    <div
      className={cn(
        "fixed top-20 right-6 z-50 max-w-sm rounded-[var(--radius)] border p-4 shadow-lg backdrop-blur-sm",
        "animate-in slide-in-from-top-2 fade-in duration-200",
        isCrisis
          ? "border-[var(--loss-red)]/50 bg-[var(--loss-red)]/20"
          : "border-[var(--border-default)] bg-[var(--bg-surface)]/95",
      )}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div
          className="mt-0.5 w-2.5 h-2.5 rounded-full shrink-0"
          style={{
            backgroundColor: BAND_COLORS[currentBand] ?? "var(--text-muted)",
          }}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {BAND_LABELS[currentBand] ?? currentBand}
            </p>
            {isCrisis && (
              <button
                onClick={dismiss}
                className="text-xs text-[var(--loss-red)] hover:text-[var(--loss-red)]/80 shrink-0"
              >
                Dismiss
              </button>
            )}
          </div>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            {BAND_DESCRIPTIONS[currentBand] ?? ""}
          </p>
          {!isCrisis && (
            <p className="text-[10px] text-[var(--text-muted)] mt-1">
              Auto-dismissing in 5s
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
