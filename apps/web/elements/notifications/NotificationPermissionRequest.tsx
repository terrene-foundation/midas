"use client";

import { useEffect, useState } from "react";
import { cn } from "@/elements/ui/utils";

type PermissionState = "default" | "granted" | "denied" | "unsupported";

const STORAGE_KEY = "midas_notif_permission_shown";

export function NotificationPermissionRequest({
  className,
}: {
  className?: string;
}) {
  const [permState, setPermState] = useState<PermissionState>("default");
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !("Notification" in window)) {
      setPermState("unsupported");
      return;
    }
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "1") {
      setDismissed(true);
      return;
    }
    setPermState(
      Notification.permission === "granted"
        ? "granted"
        : Notification.permission === "denied"
          ? "denied"
          : "default",
    );
  }, []);

  const requestPermission = async () => {
    if (!("Notification" in window)) {
      setPermState("unsupported");
      return;
    }
    try {
      const result = await Notification.requestPermission();
      setPermState(
        result === "granted"
          ? "granted"
          : result === "denied"
            ? "denied"
            : "default",
      );
      if (result !== "default") {
        localStorage.setItem(STORAGE_KEY, "1");
        setDismissed(true);
      }
    } catch {
      setPermState("default");
    }
  };

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, "1");
    setDismissed(true);
  };

  if (dismissed || permState === "unsupported") return null;

  if (permState === "granted") {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-[var(--radius)] border border-[var(--gain-green)]/30 bg-[var(--gain-green)]/10 px-4 py-3",
          className,
        )}
      >
        <svg
          className="w-4 h-4 text-[var(--gain-green)] shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
        <p className="text-sm text-[var(--gain-green)]">
          Notifications enabled
        </p>
      </div>
    );
  }

  if (permState === "denied") {
    return (
      <div
        className={cn(
          "rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-elevated)] px-4 py-3",
          className,
        )}
      >
        <p className="text-sm text-[var(--text-secondary)]">
          Browser notifications are blocked. Enable them in your browser
          settings to receive regime alerts.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-[var(--radius)] border border-[var(--accent-gold)]/30 bg-[var(--accent-gold)]/5 px-4 py-3",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Enable notifications
          </p>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            Get alerted when the market regime changes
          </p>
        </div>
        <button
          onClick={dismiss}
          className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] shrink-0"
        >
          Dismiss
        </button>
      </div>
      <button
        onClick={requestPermission}
        className="w-full rounded-[var(--radius)] bg-[var(--accent-gold)] px-4 py-2 text-sm font-medium text-[var(--bg-base)] hover:brightness-110 transition-all"
      >
        Allow notifications
      </button>
    </div>
  );
}
