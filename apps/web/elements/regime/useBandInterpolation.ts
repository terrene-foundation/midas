"use client";

import { useMemo } from "react";
import type { Band } from "@/stores/regime-store";

const BAND_COLORS: Record<Band, [number, number, number]> = {
  calm: [0x34, 0xa7, 0x7b],
  elevated: [0xd4, 0xa8, 0x43],
  urgent: [0xe8, 0x91, 0x4a],
  crisis: [0xe8, 0x5d, 0x5d],
};

const BAND_BOUNDARIES: Array<{ band: Band; low: number; high: number }> = [
  { band: "calm", low: 0.0, high: 0.25 },
  { band: "elevated", low: 0.25, high: 0.5 },
  { band: "urgent", low: 0.5, high: 0.75 },
  { band: "crisis", low: 0.75, high: 1.0 },
];

function lerpColor(
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): [number, number, number] {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

function rgbStr(c: [number, number, number]): string {
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

export function useBandInterpolation(a_t: number) {
  return useMemo(() => {
    const clamped = Math.max(0, Math.min(1, a_t));

    let currentBand: Band = "calm";
    let accentRgb: [number, number, number] = BAND_COLORS.calm;
    let nextBand: Band | null = null;

    for (let i = 0; i < BAND_BOUNDARIES.length; i++) {
      const { band, low, high } = BAND_BOUNDARIES[i];
      if (clamped >= low && clamped < high) {
        currentBand = band;
        const progress = (clamped - low) / (high - low);
        if (progress > 0.6 && i + 1 < BAND_BOUNDARIES.length) {
          const blend = (progress - 0.6) / 0.4;
          accentRgb = lerpColor(
            BAND_COLORS[band],
            BAND_COLORS[BAND_BOUNDARIES[i + 1].band],
            blend,
          );
          nextBand = BAND_BOUNDARIES[i + 1].band;
        } else if (progress < 0.4 && i > 0) {
          const blend = 1 - progress / 0.4;
          accentRgb = lerpColor(
            BAND_COLORS[band],
            BAND_COLORS[BAND_BOUNDARIES[i - 1].band],
            blend,
          );
        } else {
          accentRgb = BAND_COLORS[band];
        }
        break;
      }
      if (clamped >= 0.75) {
        currentBand = "crisis";
        accentRgb = BAND_COLORS.crisis;
      }
    }

    const decisionWeight =
      currentBand === "calm"
        ? 0.2
        : currentBand === "elevated"
          ? 0.5
          : currentBand === "urgent"
            ? 0.85
            : 1.0;

    return {
      currentBand,
      nextBand,
      accentColor: rgbStr(accentRgb),
      accentRgb,
      decisionWeight,
      progress: clamped,
      transitionDuration: 500,
    };
  }, [a_t]);
}
