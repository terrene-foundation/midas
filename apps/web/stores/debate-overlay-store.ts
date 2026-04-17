import { create } from "zustand";

interface DebateContext {
  type: string;
  id: string;
}

interface DebateOverlayState {
  isOpen: boolean;
  context: DebateContext | null;
  openDebate: (context: DebateContext) => void;
  closeDebate: () => void;
}

export const useDebateOverlayStore = create<DebateOverlayState>((set) => ({
  isOpen: false,
  context: null,
  openDebate: (context) => set({ isOpen: true, context }),
  closeDebate: () => set({ isOpen: false, context: null }),
}));
