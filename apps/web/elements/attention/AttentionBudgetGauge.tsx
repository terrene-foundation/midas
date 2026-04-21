"use client";

import { useAttention } from "@/lib/queries/usePulse";
import { useAttentionStore } from "@/stores/attention-store";
import { useEffect } from "react";
import { cn } from "@/elements/ui/utils";

const DAILY_CEILING_DEFAULT = 3600; // 60 minutes default ceiling

export function AttentionBudgetGauge({ className }: { className?: string }) {
  const { data: attention } = useAttention();
  const { decisionSecondsToday, dailyCeiling, setAttention } =
    useAttentionStore();

  useEffect(() => {
    if (attention) {
      setAttention({
        decisionSecondsToday: attention.decision_seconds_today,
        fatigueSignal: attention.fatigue_signal,
        dailyCeiling: DAILY_CEILING_DEFAULT,
      });
    }
  }, [attention, setAttention]);

  const ceiling = dailyCeiling ?? DAILY_CEILING_DEFAULT;
  const used = decisionSecondsToday;
  const usedMinutes = Math.floor(used / 60);
  const ceilingMinutes = Math.floor(ceiling / 60);
  const pct = Math.min(1, used / ceiling);

  return (
    <div
      className={cn("flex items-center gap-2 text-xs", className)}
      title={`Attention: ${usedMinutes}/${ceilingMinutes} min used`}
    >
      <span className="text-[var(--text-muted)]">Attn</span>
      <div className="relative w-16 h-1.5 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            pct > 0.85
              ? "bg-[var(--loss-red)]"
              : pct > 0.6
                ? "bg-[var(--accent-gold)]"
                : "bg-[var(--gain-green)]",
          )}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
      <span className="text-[var(--text-muted)] tabular-nums font-mono-nums">
        {usedMinutes}m
      </span>
    </div>
  );
}
