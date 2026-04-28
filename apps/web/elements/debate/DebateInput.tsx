"use client";

import { useState } from "react";
import { useAddDebateTurn } from "@/lib/queries/useDebate";
import { cn } from "@/elements/ui/utils";

interface DebateInputProps {
  threadId: string;
  disabled?: boolean;
}

export function DebateInput({ threadId, disabled }: DebateInputProps) {
  const [message, setMessage] = useState("");
  const addTurn = useAddDebateTurn();

  const handleSend = () => {
    if (!message.trim()) return;
    addTurn.mutate(
      { threadId, userMessage: message.trim() },
      { onSuccess: () => setMessage("") },
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex gap-2">
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type your argument... (Enter to send, Shift+Enter for newline)"
        disabled={disabled || addTurn.isPending}
        rows={2}
        className={cn(
          "flex-1 rounded-[var(--radius)] border border-[var(--border-default)]",
          "bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)]",
          "placeholder:text-[var(--text-muted)] resize-none",
          "focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]",
          "disabled:opacity-50 disabled:cursor-not-allowed",
        )}
      />
      <button
        onClick={handleSend}
        disabled={!message.trim() || addTurn.isPending}
        className={cn(
          "px-4 py-2 rounded-[var(--radius)] self-end",
          "bg-[var(--accent-gold)] text-[var(--bg-base)] text-sm font-medium",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "hover:opacity-90 transition-opacity",
        )}
      >
        Send
      </button>
    </div>
  );
}
