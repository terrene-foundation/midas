"use client";

import { cn } from "@/elements/ui/utils";

type ThreadStatus = "updated" | "maintained" | "open" | "envelope-change";

interface ThreadStatusBadgeProps {
  status: ThreadStatus | string;
  className?: string;
}

export function ThreadStatusBadge({
  status,
  className,
}: ThreadStatusBadgeProps) {
  const normalizedStatus = status
    .toLowerCase()
    .replace(" ", "-") as ThreadStatus;

  const config: Record<
    ThreadStatus,
    { label: string; bg: string; text: string }
  > = {
    updated: {
      label: "Updated",
      bg: "bg-[var(--gain-green)]/20",
      text: "text-[var(--gain-green)]",
    },
    maintained: {
      label: "Maintained",
      bg: "bg-[var(--regime-elevated)]/20",
      text: "text-[var(--regime-elevated)]",
    },
    open: {
      label: "Open",
      bg: "bg-[var(--bg-elevated)]",
      text: "text-[var(--text-secondary)]",
    },
    "envelope-change": {
      label: "Envelope",
      bg: "bg-[var(--accent-gold)]/20",
      text: "text-[var(--accent-gold)]",
    },
  };

  const { label, bg, text } = config[normalizedStatus] ?? {
    label: status,
    bg: "bg-[var(--bg-elevated)]",
    text: "text-[var(--text-muted)]",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
        bg,
        text,
        className,
      )}
    >
      {label}
    </span>
  );
}
