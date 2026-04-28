"use client";

import { useState } from "react";
import {
  useDebateThreads,
  useMultiTurnThread,
  useAddDebateTurn,
} from "@/lib/queries/useDebate";
import { Skeleton } from "@/elements/LoadingSkeleton";

export default function DebatePage() {
  const [selectedThread, setSelectedThread] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const { data: threadsData, isPending: threadsLoading } = useDebateThreads();
  const { data: threadData, isPending: threadLoading } = useMultiTurnThread(
    selectedThread ?? "",
  );
  const addTurn = useAddDebateTurn();

  const handleSend = () => {
    if (!selectedThread || !message.trim()) return;
    addTurn.mutate(
      { threadId: selectedThread, userMessage: message.trim() },
      { onSuccess: () => setMessage("") },
    );
  };

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">
        Debate
      </h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="space-y-2">
          <h2 className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
            Threads
          </h2>
          {threadsLoading ? (
            <Skeleton variant="card" />
          ) : (
            (threadsData?.threads ?? []).map((t) => (
              <button
                key={t.thread_id}
                onClick={() => setSelectedThread(t.thread_id)}
                className={`w-full text-left rounded-[var(--radius)] border p-3 text-sm transition-colors ${
                  selectedThread === t.thread_id
                    ? "border-[var(--accent-gold)] bg-[var(--bg-hover)]"
                    : "border-[var(--border-default)] bg-[var(--bg-surface)]"
                }`}
              >
                <p className="text-[var(--text-primary)]">
                  Thread {t.thread_id.slice(0, 8)}
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  {t.status}
                </p>
              </button>
            ))
          )}
        </div>

        <div className="lg:col-span-2">
          {threadLoading ? (
            <Skeleton variant="card" />
          ) : selectedThread && threadData ? (
            <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] flex flex-col h-[calc(100vh-200px)]">
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {(threadData.turns ?? []).map((turn, i) => (
                  <div key={turn.timestamp ?? `turn-${i}`}>
                    <div className="rounded-[var(--radius)] p-3 text-sm bg-[var(--bg-elevated)] text-[var(--text-primary)]">
                      {turn.user_message}
                    </div>
                    <div className="rounded-[var(--radius)] p-3 text-sm bg-[var(--bg-hover)] text-[var(--text-secondary)] mt-2">
                      {turn.response?.raw_content_preview ??
                        turn.response?.recommendation ??
                        ""}
                    </div>
                  </div>
                ))}
                {threadData.turns?.length === 0 && (
                  <p className="text-sm text-[var(--text-muted)] text-center py-8">
                    No messages yet. Start the debate below.
                  </p>
                )}
              </div>
              <div className="border-t border-[var(--border-default)] p-3 flex gap-2">
                <input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  placeholder="Type your argument..."
                  className="flex-1 rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
                />
                <button
                  onClick={handleSend}
                  disabled={!message.trim() || addTurn.isPending}
                  className="px-4 py-2 rounded-[var(--radius)] bg-[var(--accent-gold)] text-[var(--bg-base)] text-sm font-medium disabled:opacity-50"
                >
                  Send
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-8 text-center">
              <p className="text-sm text-[var(--text-muted)]">
                Select a thread to view the debate
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
