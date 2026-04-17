"use client";

import { cn } from "@/elements/ui/utils";

interface RegimeGaugeProps {
  a_t: number;
  transitionPressure?: number;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const BAND_MARKERS = [
  { position: 12.5, color: "var(--regime-calm)", label: "Calm" },
  { position: 37.5, color: "var(--regime-elevated)", label: "Elevated" },
  { position: 62.5, color: "var(--regime-urgent)", label: "Urgent" },
  { position: 87.5, color: "var(--regime-crisis)", label: "Crisis" },
];

export function RegimeGauge({
  a_t,
  transitionPressure,
  size = "md",
  className,
}: RegimeGaugeProps) {
  const clamped = Math.max(0, Math.min(1, a_t));
  const position = clamped * 100;

  return (
    <div
      className={cn(
        "relative w-full",
        size === "sm" && "h-2",
        size === "md" && "h-3",
        size === "lg" && "h-4",
        className,
      )}
    >
      <div className="absolute inset-0 rounded-full overflow-hidden flex">
        <div
          className="h-full"
          style={{
            width: "25%",
            background: "var(--regime-calm)",
            opacity: 0.3,
          }}
        />
        <div
          className="h-full"
          style={{
            width: "25%",
            background: "var(--regime-elevated)",
            opacity: 0.3,
          }}
        />
        <div
          className="h-full"
          style={{
            width: "25%",
            background: "var(--regime-urgent)",
            opacity: 0.3,
          }}
        />
        <div
          className="h-full"
          style={{
            width: "25%",
            background: "var(--regime-crisis)",
            opacity: 0.3,
          }}
        />
      </div>

      <div
        className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-full bg-white shadow-lg transition-[left] duration-500 ease-out"
        style={{
          left: `${position}%`,
          width: size === "sm" ? 8 : size === "md" ? 12 : 16,
          height: size === "sm" ? 8 : size === "md" ? 12 : 16,
        }}
      />

      {transitionPressure != null && transitionPressure > 0.1 && (
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-[var(--accent-gold)] opacity-70"
          style={{
            left: `${Math.min(99, position + transitionPressure * 8)}%`,
          }}
        />
      )}

      {size === "lg" && (
        <div className="flex justify-between mt-1 px-0.5">
          {BAND_MARKERS.map((m) => (
            <span
              key={m.label}
              className="text-[9px] text-[var(--text-muted)]"
              style={{ width: "25%", textAlign: "center" }}
            >
              {m.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
