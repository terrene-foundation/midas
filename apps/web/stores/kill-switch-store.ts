import { create } from "zustand";

interface KillSwitchState {
  isActive: boolean;
  confirmationCode: string | null;
  setActive: (code?: string) => void;
  clear: () => void;
}

export const useKillSwitchStore = create<KillSwitchState>((set) => ({
  isActive: false,
  confirmationCode: null,
  setActive: (code) => set({ isActive: true, confirmationCode: code ?? null }),
  clear: () => set({ isActive: false, confirmationCode: null }),
}));
