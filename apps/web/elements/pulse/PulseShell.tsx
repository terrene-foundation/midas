"use client";

import { useRegimeStore, type Band } from "@/stores/regime-store";
import { useRegime, usePulse } from "@/lib/queries/usePulse";
import { useEffect, useMemo } from "react";
import { PulseSkeleton } from "@/elements/LoadingSkeleton";
import { PulseCalmLayout } from "./PulseCalmLayout";
import { PulseElevatedLayout } from "./PulseElevatedLayout";
import { PulseUrgentLayout } from "./PulseUrgentLayout";
import { PulseCrisisLayout } from "./PulseCrisisLayout";

function deriveLayoutBand(a_t: number): Band {
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

  const BAND_ORDER: Band[] = ["calm", "elevated", "urgent", "crisis"];

  // Active band at full opacity; adjacent bands at 0.15 for soft cross-fade.
  // The 500ms CSS transition creates a smooth drift effect between bands.
  const opacityFor = (band: Band) => {
    if (band === primaryBand) return 1;
    const distance = Math.abs(
      BAND_ORDER.indexOf(band) - BAND_ORDER.indexOf(primaryBand),
    );
    return distance === 1 ? 0.15 : 0;
  };

  return (
    <div className="relative">
      {BAND_ORDER.map((band) => (
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
