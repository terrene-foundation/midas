"use client";

import { useState } from "react";
import { useSignals } from "@/lib/queries/useSignal";
import type { Signal } from "@/lib/types";
import { SignalCard } from "./SignalCard";
import { SignalDetailSheet } from "./SignalDetailSheet";
import { cn } from "@/elements/ui/utils";

interface SignalListProps {
  className?: string;
}

export function SignalList({ className }: SignalListProps) {
  const { data, isPending } = useSignals();
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);
  const [filter, setFilter] = useState<{
    ticker?: string;
    impactLevel?: "high" | "medium" | "low" | "none";
  }>({});

  const signals = data?.signals ?? [];

  // Sort by portfolio impact (high first)
  const sortedSignals = [...signals].sort((a, b) => b.strength - a.strength);

  // Filter signals
  const filteredSignals = sortedSignals.filter((s) => {
    if (
      filter.ticker &&
      !s.instrument.toLowerCase().includes(filter.ticker.toLowerCase())
    ) {
      return false;
    }
    if (filter.impactLevel) {
      const impactLevel =
        s.strength >= 0.7
          ? "high"
          : s.strength >= 0.4
            ? "medium"
            : s.strength >= 0.2
              ? "low"
              : "none";
      if (impactLevel !== filter.impactLevel) return false;
    }
    return true;
  });

  return (
    <>
      <div className={cn("space-y-3", className)}>
        {/* Filter bar */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Filter by ticker..."
            value={filter.ticker ?? ""}
            onChange={(e) =>
              setFilter((f) => ({ ...f, ticker: e.target.value || undefined }))
            }
            className="flex-1 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
          />
          <select
            value={filter.impactLevel ?? ""}
            onChange={(e) =>
              setFilter((f) => ({
                ...f,
                impactLevel: (e.target.value ||
                  undefined) as typeof f.impactLevel,
              }))
            }
            className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-1.5 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
          >
            <option value="">All impacts</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="none">None</option>
          </select>
        </div>

        {/* Signal count */}
        <p className="text-xs text-[var(--text-muted)]">
          {filteredSignals.length} signals
          {filter.ticker && ` matching "${filter.ticker}"`}
        </p>

        {/* Signal list */}
        {isPending ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-20 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] animate-pulse"
              />
            ))}
          </div>
        ) : filteredSignals.length === 0 ? (
          <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-8 text-center">
            <p className="text-sm text-[var(--text-muted)]">
              No signals match your filters
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredSignals.map((signal) => (
              <SignalCard
                key={signal.id}
                signal={signal}
                onClick={() => setSelectedSignal(signal)}
              />
            ))}
          </div>
        )}
      </div>

      <SignalDetailSheet
        signal={selectedSignal}
        onClose={() => setSelectedSignal(null)}
      />
    </>
  );
}
