"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api-client";

interface ReAuthModalProps {
  open: boolean;
  onResult: (success: boolean) => void;
  reason?: string;
}

export function ReAuthModal({ open, onResult, reason }: ReAuthModalProps) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (!password) {
        onResult(false);
        return;
      }
      await api.post("/auth/reauth", { password });
      onResult(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Incorrect password. Please try again.");
      } else {
        setError("Verification failed. Please try again.");
      }
      onResult(false);
    } finally {
      setLoading(false);
      setPassword("");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6 space-y-4 animate-fade-in">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          Confirm Action
        </h2>
        {reason && (
          <p className="text-sm text-[var(--text-secondary)]">{reason}</p>
        )}
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter password to confirm"
            className="w-full rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
            autoFocus
          />
          {error && <p className="text-xs text-[var(--loss-red)]">{error}</p>}
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={() => onResult(false)}
              className="px-4 py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !password}
              className="px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-base)] disabled:opacity-50 transition-colors"
            >
              {loading ? "Verifying..." : "Confirm"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
