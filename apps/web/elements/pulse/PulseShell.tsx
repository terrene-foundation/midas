"use client";

import { useRegimeStore } from "@/stores/regime-store";
import { useRegime, usePulse } from "@/lib/queries/usePulse";
import { useEffect, useMemo } from "react";
import { PulseSkeleton } from "@/elements/LoadingSkeleton";
import { PulseCalmLayout } from "./PulseCalmLayout";
import { PulseElevatedLayout } from "./PulseElevatedLayout";
import { PulseUrgentLayout } from "./PulseUrgentLayout";
import { PulseCrisisLayout } from "./PulseCrisisLayout";

type LayoutBand = "calm" | "elevated" | "urgent" | "crisis";

function deriveLayoutBand(a_t: number): LayoutBand {
  if (a_t < 0.25) return "calm";
  if (a_t < 0.5) return "elevated";
  if (a_t < 0.75) return "urgent";
  return "crisis";
}

export function PulseShell() {
  const { data: regime } = useRegime();
  const { data: pulse, isPending } = usePulse();
  const { a_t, setRegime } = useRegimeStore();

  useEffect(() => {
    if (regime) {
      setRegime({
        a_t: regime.a_t,
        band: regime.band,
        changepointProbability: regime.changepoint_probability,
        oodScore: regime.ood_score,
        z_t_posterior: regime.z_t_posterior,
      });
    }
  }, [regime, setRegime]);

  const primaryBand = useMemo(() => deriveLayoutBand(a_t), [a_t]);

  if (isPending) return <PulseSkeleton />;

  // Render all four layouts stacked with opacity transitions.
  // The active band gets opacity 1; neighbors get a soft fade
  // so transitions between bands are perceived as drift (500ms).
  const opacityFor = (band: LayoutBand) => {
    if (band === primaryBand) return 1;
    // Partially visible neighbor for soft cross-fade
    const bandIndex = { calm: 0, elevated: 1, urgent: 2, crisis: 3 }[band];
    const primaryIndex = { calm: 0, elevated: 1, urgent: 2, crisis: 3 }[
      primaryBand
    ];
    const distance = Math.abs(bandIndex - primaryIndex);
    if (distance === 1) return 0;
    return 0;
  };

  return (
    <div className="relative">
      {(["calm", "elevated", "urgent", "crisis"] as const).map((band) => (
        <div
          key={band}
          className="transition-opacity ease-out"
          style={{
            opacity: opacityFor(band),
            position: band === primaryBand ? "relative" : "absolute",
            inset: band !== primaryBand ? 0 : undefined,
            pointerEvents: band === primaryBand ? "auto" : "none",
            transitionDuration: "var(--transition-regime)",
          }}
        >
          {band === "calm" && <PulseCalmLayout pulse={pulse} />}
          {band === "elevated" && <PulseElevatedLayout pulse={pulse} />}
          {band === "urgent" && <PulseUrgentLayout pulse={pulse} />}
          {band === "crisis" && <PulseCrisisLayout pulse={pulse} />}
        </div>
      ))}
    </div>
  );
}
