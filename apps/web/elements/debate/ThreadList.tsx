"use client";

import { useDebateThreads } from "@/lib/queries/useDebate";
import { ThreadCard } from "./ThreadCard";
import { Skeleton } from "@/elements/LoadingSkeleton";

interface ThreadListProps {
  onSelectThread?: (threadId: string) => void;
  selectedThreadId?: string | null;
}

export function ThreadList({
  onSelectThread,
  selectedThreadId,
}: ThreadListProps) {
  const { data: threadsData, isPending } = useDebateThreads();

  if (isPending) {
    return (
      <div className="space-y-2">
        <Skeleton variant="card" />
        <Skeleton variant="card" />
        <Skeleton variant="card" />
      </div>
    );
  }

  const threads = threadsData?.threads ?? [];

  if (threads.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-[var(--text-muted)]">No threads yet</p>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Start a debate from a decision
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {threads.map((thread) => (
        <ThreadCard
          key={thread.thread_id}
          thread={thread}
          onClick={() => onSelectThread?.(thread.thread_id)}
          selected={selectedThreadId === thread.thread_id}
        />
      ))}
    </div>
  );
}
