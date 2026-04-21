"use client";

import type { BacktestResult } from "@/lib/types";

interface EquityCurveProps {
  data: Array<{ date: string; value: number }> | undefined;
}

export function EquityCurve({ data }: EquityCurveProps) {
  if (!data || data.length === 0) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-3">
          Equity Curve
        </p>
        <div className="h-48 flex items-center justify-center">
          <p className="text-sm text-[var(--text-muted)]">
            No equity curve data
          </p>
        </div>
      </div>
    );
  }

  const minVal = Math.min(...data.map((d) => d.value));
  const maxVal = Math.max(...data.map((d) => d.value));
  const range = maxVal - minVal || 1;
  const firstVal = data[0]?.value ?? 0;
  const lastVal = data[data.length - 1]?.value ?? 0;
  const isPositive = lastVal >= firstVal;

  const width = 100;
  const height = 100;
  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((d.value - minVal) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  const areaPoints = `0,${height} ${points} ${width},${height}`;

  const xLabels = [0, Math.floor(data.length / 2), data.length - 1].map((i) => {
    const d = data[i];
    if (!d) return { x: 0, label: "" };
    const x = (i / (data.length - 1)) * 100;
    const label = new Date(d.date).toLocaleDateString("en-US", {
      month: "short",
      year: "2-digit",
    });
    return { x, label };
  });

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
          Equity Curve
        </p>
        <p
          className={`text-xs font-mono-nums tabular-nums ${isPositive ? "text-[var(--gain-green)]" : "text-[var(--loss-red)]"}`}
        >
          {isPositive ? "+" : ""}
          {((lastVal / firstVal - 1) * 100).toFixed(2)}%
        </p>
      </div>

      <div className="relative h-48">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-full"
          preserveAspectRatio="none"
        >
          {/* Grid lines */}
          {[0, 25, 50, 75, 100].map((pct) => (
            <line
              key={pct}
              x1="0"
              y1={`${pct}%`}
              x2="100%"
              y2={`${pct}%`}
              stroke="var(--border-default)"
              strokeWidth="0.3"
              strokeDasharray="2,2"
            />
          ))}

          {/* Area fill */}
          <polygon
            points={areaPoints}
            fill={isPositive ? "var(--gain-green)" : "var(--loss-red)"}
            opacity="0.1"
          />

          {/* Line */}
          <polyline
            points={points}
            fill="none"
            stroke={isPositive ? "var(--gain-green)" : "var(--loss-red)"}
            strokeWidth="0.8"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </svg>

        {/* X-axis labels */}
        <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] text-[var(--text-muted)]">
          {xLabels.map((l, i) => (
            <span
              key={i}
              style={{
                position: "absolute",
                left: `${l.x}%`,
                transform: "translateX(-50%)",
              }}
            >
              {l.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
