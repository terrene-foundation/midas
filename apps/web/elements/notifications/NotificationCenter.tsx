"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api-client";
import {
  NotificationList,
  type NotificationItemData,
} from "./NotificationList";
import { cn } from "@/elements/ui/utils";

interface NotificationResponse {
  items: NotificationItemData[];
  total: number;
  unread_count: number;
  limit: number;
  offset: number;
}

const POLL_INTERVAL_MS = 30_000; // Poll every 30s for real-time updates

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItemData[]>(
    [],
  );
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const bellRef = useRef<HTMLButtonElement>(null);

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await api.get<NotificationResponse>("/notifications/");
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
    }
  }, []);

  const markRead = useCallback(async (id: number) => {
    await api.patch(`/notifications/${id}/read`);
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
    );
    setUnreadCount((prev) => Math.max(0, prev - 1));
  }, []);

  const markAllRead = useCallback(async () => {
    await api.post("/notifications/mark-all-read");
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnreadCount(0);
  }, []);

  const deleteNotification = useCallback(
    async (id: number) => {
      await api.delete(`/notifications/${id}`);
      const notif = notifications.find((n) => n.id === id);
      setNotifications((prev) => prev.filter((n) => n.id !== id));
      if (notif && !notif.read) {
        setUnreadCount((prev) => Math.max(0, prev - 1));
      }
    },
    [notifications],
  );

  // Initial fetch and polling
  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        !bellRef.current?.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open]);

  return (
    <div className="relative">
      {/* Bell button */}
      <button
        ref={bellRef}
        onClick={() => setOpen((o) => !o)}
        className="relative flex items-center justify-center w-9 h-9 rounded-[var(--radius)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
        aria-label="Notifications"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <path
            d="M9 2a5 5 0 0 0-5 5v3.586l-.707.707A1 1 0 0 0 4 13h10a1 1 0 0 0 .707-1.707L14 10.586V7a5 5 0 0 0-5-5ZM9 16a2 2 0 1 1 0-4 2 2 0 0 1 0 4Z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[16px] h-4 px-1 text-[10px] font-medium rounded-full bg-[var(--accent-gold)] text-[var(--bg-base)]">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div
          ref={dropdownRef}
          className={cn(
            "absolute right-0 top-full mt-2 z-50",
            "w-[380px] max-h-[520px]",
            "bg-[var(--bg-surface)] border border-[var(--border-default)]",
            "rounded-[var(--radius)] shadow-lg shadow-black/20",
            "flex flex-col overflow-hidden",
            "animate-in fade-in slide-in-from-top-2 duration-150",
          )}
        >
          <NotificationList
            notifications={notifications}
            unreadCount={unreadCount}
            onMarkRead={markRead}
            onDelete={deleteNotification}
            onMarkAllRead={markAllRead}
            loading={loading}
          />
        </div>
      )}
    </div>
  );
}
