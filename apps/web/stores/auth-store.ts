import { create } from "zustand";

interface AuthState {
  isAuthenticated: boolean;
  user: { email: string } | null;
  token: string | null;
  login: (token: string, email: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: false,
  user: null,
  token: null,
  login: (token, email) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("midas_token", token);
      localStorage.setItem("midas_email", email);
      document.cookie = `midas_token=${token}; path=/; max-age=${60 * 60 * 24}; SameSite=Strict`;
    }
    set({ isAuthenticated: true, token, user: { email } });
  },
  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("midas_token");
      localStorage.removeItem("midas_email");
      document.cookie = "midas_token=; path=/; max-age=0";
    }
    set({ isAuthenticated: false, token: null, user: null });
  },
}));
