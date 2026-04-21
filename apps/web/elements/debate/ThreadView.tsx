"use client";

import { useDebateThread } from "@/lib/queries/useDebate";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { MessageBubble } from "./MessageBubble";
import { DebateInput } from "./DebateInput";
import { ToolActionBar } from "./ToolActionBar";
import { ResolutionBanner } from "./ResolutionBanner";
import { InlineVisualization } from "./InlineVisualization";
import { ThreadStatusBadge } from "./ThreadStatusBadge";
import { cn } from "@/elements/ui/utils";

interface ThreadViewProps {
  threadId: string;
  onClose?: () => void;
}

export function ThreadView({ threadId, onClose }: ThreadViewProps) {
  const { data: threadData, isPending } = useDebateThread(threadId);

  if (isPending) {
    return (
      <div className="flex flex-col h-full">
        <div className="p-4 border-b border-[var(--border-default)]">
          <Skeleton className="h-6 w-48" />
        </div>
        <div className="flex-1 p-4 space-y-3">
          <Skeleton variant="rect" className="h-24" />
          <Skeleton variant="rect" className="h-32" />
          <Skeleton variant="rect" className="h-24" />
        </div>
      </div>
    );
  }

  if (!threadData) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-[var(--text-muted)]">Thread not found</p>
      </div>
    );
  }

  const messages = threadData.messages ?? [];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-default)]">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Thread {threadId.slice(0, 8)}
          </h2>
          <ThreadStatusBadge status={threadData.status} />
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Close thread"
          >
            ✕
          </button>
        )}
      </div>

      {/* Resolution Banner */}
      {threadData.status !== "open" && (
        <div className="px-4 py-2">
          <ResolutionBanner state={threadData.status} />
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <p className="text-sm text-[var(--text-muted)]">No messages yet</p>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Start the debate below
            </p>
          </div>
        ) : (
          messages.map((message, i) => (
            <div key={message.id ?? `msg-${i}`}>
              {message.content.startsWith("[VISUALIZATION]") ? (
                (() => {
                  try {
                    const vizData = JSON.parse(
                      message.content.replace("[VISUALIZATION]", "").trim(),
                    );
                    return <InlineVisualization data={vizData} />;
                  } catch {
                    return <MessageBubble message={message} />;
                  }
                })()
              ) : (
                <MessageBubble message={message} />
              )}
            </div>
          ))
        )}
      </div>

      {/* Tool Action Bar */}
      <div className="px-4 py-2 border-t border-[var(--border-default)]">
        <ToolActionBar threadId={threadId} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-[var(--border-default)]">
        <DebateInput threadId={threadId} />
      </div>
    </div>
  );
}
