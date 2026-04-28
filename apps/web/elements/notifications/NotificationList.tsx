"use client";

import { useState, useCallback } from "react";
import {
  NotificationItem,
  type NotificationItemData,
} from "./NotificationItem";
import { cn } from "@/elements/ui/utils";

interface NotificationListProps {
  notifications: NotificationItemData[];
  unreadCount: number;
  onMarkRead: (id: number) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onMarkAllRead: () => Promise<void>;
  loading?: boolean;
}

export function NotificationList({
  notifications,
  unreadCount,
  onMarkRead,
  onDelete,
  onMarkAllRead,
  loading = false,
}: NotificationListProps) {
  const [filter, setFilter] = useState<"all" | "unread">("all");

  const filtered =
    filter === "unread" ? notifications.filter((n) => !n.read) : notifications;

  const handleMarkRead = useCallback(
    async (id: number) => {
      await onMarkRead(id);
    },
    [onMarkRead],
  );

  const handleDelete = useCallback(
    async (id: number) => {
      await onDelete(id);
    },
    [onDelete],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 border-2 border-[var(--accent-gold)] border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-[var(--text-muted)]">
            Loading notifications...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-default)]">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Notifications
          </h2>
          {unreadCount > 0 && (
            <span className="flex items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-medium rounded-full bg-[var(--accent-gold)] text-[var(--bg-base)]">
              {unreadCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFilter((f) => (f === "all" ? "unread" : "all"))}
            className="px-2 py-1 text-xs rounded border border-[var(--border-default)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent-gold)] transition-colors"
          >
            {filter === "all" ? "All" : "Unread"}
          </button>
          {unreadCount > 0 && (
            <button
              onClick={onMarkAllRead}
              className="px-2 py-1 text-xs rounded border border-[var(--border-default)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent-gold)] transition-colors"
            >
              Mark all read
            </button>
          )}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-10 h-10 rounded-full bg-[var(--bg-elevated)] flex items-center justify-center mb-3">
              <svg
                width="20"
                height="20"
                viewBox="0 0 20 20"
                fill="none"
                className="text-[var(--text-muted)]"
              >
                <path
                  d="M10 2a6 6 0 0 0-6 6v3.586l-.707.707A1 1 0 0 0 4 14h12a1 1 0 0 0 .707-1.707L16 11.586V8a6 6 0 0 0-6-6ZM10 18a2 2 0 1 1 0-4 2 2 0 0 1 0 4Z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <p className="text-sm text-[var(--text-secondary)]">
              {filter === "unread"
                ? "No unread notifications"
                : "No notifications yet"}
            </p>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              {filter === "unread"
                ? "All caught up!"
                : "Notifications will appear here when something needs your attention"}
            </p>
          </div>
        ) : (
          <div>
            {filtered.map((notification) => (
              <NotificationItem
                key={notification.id}
                notification={notification}
                onMarkRead={handleMarkRead}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
