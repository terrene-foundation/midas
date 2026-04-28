import { create } from "zustand";

interface DebateContext {
  type: string;
  id: string;
}

interface DebateOverlayState {
  isOpen: boolean;
  context: DebateContext | null;
  threadId: string | null;
  openDebate: (context: DebateContext) => void;
  setThreadId: (threadId: string) => void;
  closeDebate: () => void;
}

export const useDebateOverlayStore = create<DebateOverlayState>((set) => ({
  isOpen: false,
  context: null,
  threadId: null,
  openDebate: (context) => set({ isOpen: true, context, threadId: null }),
  setThreadId: (threadId) => set({ threadId }),
  closeDebate: () => set({ isOpen: false, context: null, threadId: null }),
}));
