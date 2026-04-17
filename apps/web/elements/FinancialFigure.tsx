"use client";

import { cn } from "@/elements/ui/utils";

interface FinancialFigureProps {
  value: number;
  format?: "percent" | "currency" | "number";
  className?: string;
  showSign?: boolean;
}

export function FinancialFigure({
  value,
  format = "percent",
  className,
  showSign = true,
}: FinancialFigureProps) {
  const isPositive = value > 0;
  const isZero = value === 0;

  const colorClass = isZero
    ? "text-[var(--text-secondary)]"
    : isPositive
      ? "text-[var(--gain-green)]"
      : "text-[var(--loss-red)]";

  let display: string;
  switch (format) {
    case "percent":
      display =
        isPositive && showSign
          ? `+${value.toFixed(2)}%`
          : `${value.toFixed(2)}%`;
      break;
    case "currency": {
      const prefix = isPositive && showSign ? "+$" : "-$";
      display = isZero
        ? `$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2 })}`
        : `${prefix}${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
      break;
    }
    case "number":
      display =
        isPositive && showSign
          ? `+${value.toLocaleString("en-US")}`
          : value.toLocaleString("en-US");
      break;
  }

  return (
    <span
      className={cn(
        "font-mono-nums font-medium tabular-nums",
        colorClass,
        className,
      )}
    >
      {display}
    </span>
  );
}
