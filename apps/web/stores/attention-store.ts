import { create } from "zustand";

interface AttentionState {
  decisionSecondsToday: number;
  fatigueSignal: boolean;
  dailyCeiling: number | null;
  setAttention: (data: {
    decisionSecondsToday?: number;
    fatigueSignal?: boolean;
    dailyCeiling?: number | null;
  }) => void;
}

export const useAttentionStore = create<AttentionState>((set) => ({
  decisionSecondsToday: 0,
  fatigueSignal: false,
  dailyCeiling: null,
  setAttention: (data) => set(data),
}));
