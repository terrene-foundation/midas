import { create } from "zustand";

export type Band = "calm" | "elevated" | "urgent" | "crisis";

interface RegimeState {
  a_t: number;
  band: Band;
  changepointProbability: number;
  oodScore: number;
  transitionPressure: number;
  z_t_posterior: number[];
  setRegime: (data: {
    a_t: number;
    band?: Band;
    changepointProbability?: number;
    oodScore?: number;
    transitionPressure?: number;
    z_t_posterior?: number[];
  }) => void;
}

function deriveBand(a_t: number): Band {
  // Thresholds MUST match RegimeRenderer.get_band() in src/midas/regime/__init__.py
  if (a_t < 0.3) return "calm";
  if (a_t < 0.6) return "elevated";
  if (a_t < 0.85) return "urgent";
  return "crisis";
}

export const useRegimeStore = create<RegimeState>((set) => ({
  a_t: 0.0,
  band: "calm",
  changepointProbability: 0.0,
  oodScore: 0.0,
  transitionPressure: 0.0,
  z_t_posterior: [],
  setRegime: (data) =>
    set({
      ...data,
      band: data.band ?? deriveBand(data.a_t),
    }),
}));
