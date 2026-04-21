"use client";

import { cn } from "@/elements/ui/utils";

interface MessageBubbleProps {
  message: {
    id: string;
    content: string;
    role: "user" | "agent";
    severity?: string;
    provenance_pointers?: Array<{
      source: string;
      reference: string;
      snippet?: string;
    }>;
  };
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user" || message.severity === "user";

  return (
    <div
      className={cn(
        "rounded-[var(--radius)] p-4 space-y-2",
        isUser
          ? "bg-[var(--bg-elevated)] text-[var(--text-primary)]"
          : "bg-[var(--bg-hover)] text-[var(--text-secondary)]",
      )}
    >
      <div className="flex items-center gap-2 mb-1">
        <span
          className={cn(
            "text-xs font-medium uppercase tracking-wider",
            isUser ? "text-[var(--text-muted)]" : "text-[var(--accent-gold)]",
          )}
        >
          {isUser ? "You" : "Agent"}
        </span>
      </div>

      <div className="text-sm leading-relaxed whitespace-pre-wrap">
        {message.content}
      </div>

      {!isUser &&
        message.provenance_pointers &&
        message.provenance_pointers.length > 0 && (
          <div className="mt-3 pt-3 border-t border-[var(--border-default)] space-y-2">
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
              Provenance
            </p>
            {message.provenance_pointers.map((pointer, i) => (
              <div key={i} className="text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-[var(--accent-gold)]">
                    {pointer.source}
                  </span>
                  <span className="text-[var(--text-muted)]">
                    {pointer.reference}
                  </span>
                </div>
                {pointer.snippet && (
                  <p className="mt-1 text-[var(--text-muted)] italic">
                    &ldquo;{pointer.snippet}&rdquo;
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
    </div>
  );
}
