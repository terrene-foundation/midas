"use client";

import { cn } from "@/elements/ui/utils";
import { Bell, TrendingUp, RefreshCw, AlertTriangle } from "lucide-react";

export interface NotificationItemData {
  id: number;
  user_id: string;
  notification_type: "PORTFOLIO_ALERT" | "REGIME_CHANGE" | "TRADE_CONFIRMATION";
  title: string;
  body: string;
  read: boolean;
  metadata_json: string;
  created_at: string;
}

interface NotificationItemProps {
  notification: NotificationItemData;
  onMarkRead: (id: number) => void;
  onDelete: (id: number) => void;
}

const TYPE_CONFIG = {
  PORTFOLIO_ALERT: {
    icon: TrendingUp,
    color: "text-[var(--accent-gold)]",
    bg: "bg-[var(--accent-gold)]/10",
  },
  REGIME_CHANGE: {
    icon: RefreshCw,
    color: "text-blue-400",
    bg: "bg-blue-400/10",
  },
  TRADE_CONFIRMATION: {
    icon: Bell,
    color: "text-[var(--gain-green)]",
    bg: "bg-[var(--gain-green)]/10",
  },
} as const;

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export function NotificationItem({
  notification,
  onMarkRead,
  onDelete,
}: NotificationItemProps) {
  const config = TYPE_CONFIG[notification.notification_type];
  const Icon = config.icon;
  const metadata = (() => {
    try {
      return JSON.parse(notification.metadata_json || "{}");
    } catch {
      return {};
    }
  })();

  return (
    <div
      className={cn(
        "group relative flex items-start gap-3 px-4 py-3 border-b border-[var(--border-default)] transition-colors",
        !notification.read && "bg-[var(--bg-hover)]",
        "hover:bg-[var(--bg-elevated)]",
      )}
    >
      {/* Unread dot */}
      {!notification.read && (
        <div className="absolute left-2 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-[var(--accent-gold)]" />
      )}

      {/* Icon */}
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-0.5",
          config.bg,
        )}
      >
        <Icon size={14} className={config.color} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <p
            className={cn(
              "text-sm truncate",
              notification.read
                ? "text-[var(--text-secondary)]"
                : "text-[var(--text-primary)] font-medium",
            )}
          >
            {notification.title}
          </p>
          <span className="flex-shrink-0 text-xs text-[var(--text-muted)]">
            {formatRelativeTime(notification.created_at)}
          </span>
        </div>
        <p className="text-xs text-[var(--text-muted)] mt-0.5 line-clamp-2">
          {notification.body}
        </p>
        {metadata.instrument && (
          <p className="text-xs text-[var(--accent-gold)] mt-1 font-mono">
            {metadata.instrument}
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {!notification.read && (
          <button
            onClick={() => onMarkRead(notification.id)}
            className="p-1 rounded hover:bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            title="Mark as read"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <circle
                cx="6"
                cy="6"
                r="5"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <path
                d="M3.5 6l1.5 1.5 3-3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
        <button
          onClick={() => onDelete(notification.id)}
          className="p-1 rounded hover:bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-red-400"
          title="Delete"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M2 3h8M4 3V2h4v1M5 5v4M7 5v4M3 3l.5 7h5l.5-7"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}
