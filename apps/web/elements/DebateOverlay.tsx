"use client";

import { useDebateOverlayStore } from "@/stores/debate-overlay-store";
import { useDebateThread, useAddMessage } from "@/lib/queries/useDebate";
import { useState } from "react";

export function DebateOverlay() {
  const { isOpen, context, closeDebate } = useDebateOverlayStore();
  const [message, setMessage] = useState("");

  const threadId = context?.id ?? "";
  const { data: threadData } = useDebateThread(isOpen ? threadId : "");
  const addMessage = useAddMessage();

  if (!isOpen) return null;

  const handleSend = () => {
    if (!threadId || !message.trim()) return;
    addMessage.mutate(
      { threadId, content: message.trim() },
      { onSuccess: () => setMessage("") },
    );
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={closeDebate} />
      <div className="relative w-full max-w-md h-full bg-[var(--bg-surface)] border-l border-[var(--border-default)] flex flex-col animate-fade-in">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-default)]">
          <h2 className="text-sm font-semibold text-[var(--accent-gold)]">
            Debate{context ? ` — ${context.type}` : ""}
          </h2>
          <button
            onClick={closeDebate}
            className="p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Close debate panel"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {(threadData?.messages ?? []).map((m, i) => (
            <div
              key={m.id ?? `msg-${i}`}
              className={`rounded-[var(--radius)] p-3 text-sm ${
                ("role" in m && m.role === "user") || m.severity === "user"
                  ? "bg-[var(--bg-elevated)] text-[var(--text-primary)]"
                  : "bg-[var(--bg-hover)] text-[var(--text-secondary)]"
              }`}
            >
              {m.content}
            </div>
          ))}
          {!threadData?.messages?.length && (
            <p className="text-sm text-[var(--text-muted)] text-center py-8">
              No messages yet
            </p>
          )}
        </div>

        <div className="border-t border-[var(--border-default)] p-3 flex gap-2">
          <input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Type your argument..."
            aria-label="Debate message input"
            className="flex-1 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
          />
          <button
            onClick={handleSend}
            disabled={!message.trim() || addMessage.isPending}
            className="px-4 py-2 rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-base)] text-sm font-medium disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
