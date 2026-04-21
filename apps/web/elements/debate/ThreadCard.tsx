"use client";

import { cn } from "@/elements/ui/utils";
import { ThreadStatusBadge } from "./ThreadStatusBadge";

interface ThreadCardProps {
  thread: {
    thread_id: string;
    decision_id?: string;
    status: string;
    originating_context?: string;
    last_activity?: string;
  };
  onClick?: () => void;
  selected?: boolean;
}

export function ThreadCard({ thread, onClick, selected }: ThreadCardProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-[var(--radius)] border p-3 transition-colors",
        selected
          ? "border-[var(--accent-gold)] bg-[var(--bg-hover)]"
          : "border-[var(--border-default)] bg-[var(--bg-surface)]",
        "hover:border-[var(--accent-gold)]/50",
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
          {thread.originating_context ??
            `Thread ${thread.thread_id.slice(0, 8)}`}
        </p>
        <ThreadStatusBadge status={thread.status} />
      </div>

      {thread.decision_id && (
        <p className="text-xs text-[var(--text-muted)] mb-1">
          Decision: {thread.decision_id.slice(0, 8)}
        </p>
      )}

      {thread.last_activity && (
        <p className="text-xs text-[var(--text-muted)]">
          {formatRelativeTime(thread.last_activity)}
        </p>
      )}
    </button>
  );
}

function formatRelativeTime(timestamp: string): string {
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now.getTime() - then.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return then.toLocaleDateString();
}
