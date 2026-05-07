"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useNotificationPreferences,
  useUpdateNotificationPreferences,
  NOTIF_KEY,
} from "@/lib/queries/useNotifications";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";
import type { NotificationTier } from "@/lib/types";

const BANDS = [
  { id: "calm", label: "Calm", color: "var(--regime-calm)" },
  { id: "elevated", label: "Elevated", color: "var(--regime-elevated)" },
  { id: "urgent", label: "Urgent", color: "var(--regime-urgent)" },
  { id: "crisis", label: "Crisis", color: "var(--regime-crisis)" },
];

// Map boolean toggles (per-band notification enabled/disabled) to tier strings
const TIER_ENABLED: NotificationTier = "standard_push";
const TIER_DISABLED: NotificationTier = "silent_in_app";

function bandTiersToEnabled(
  tiers: Record<string, NotificationTier>,
): Record<string, boolean> {
  return {
    calm: tiers.calm !== "silent_in_app",
    elevated: tiers.elevated !== "silent_in_app",
    urgent: tiers.urgent !== "silent_in_app",
    crisis: tiers.crisis !== "silent_in_app",
  };
}

function enabledToBandTiers(
  enabled: Record<string, boolean>,
): Record<string, NotificationTier> {
  return {
    calm: enabled.calm ? TIER_ENABLED : TIER_DISABLED,
    elevated: enabled.elevated ? TIER_ENABLED : TIER_DISABLED,
    urgent: enabled.urgent ? TIER_ENABLED : TIER_DISABLED,
    crisis: enabled.crisis ? TIER_ENABLED : TIER_DISABLED,
  };
}

export function NotificationPreferences({ className }: { className?: string }) {
  const qc = useQueryClient();
  const { data: prefs, isPending } = useNotificationPreferences();
  const update = useUpdateNotificationPreferences();

  const [dailyCeiling, setDailyCeiling] = useState(30);
  const [bandTiers, setBandTiers] = useState<Record<string, boolean>>({
    calm: false,
    elevated: true,
    urgent: true,
    crisis: true,
  });
  const [quietStart, setQuietStart] = useState("22:00");
  const [quietEnd, setQuietEnd] = useState("07:00");
  const [saved, setSaved] = useState(false);

  // Sync local state when server data arrives
  if (!isPending && prefs) {
    const enabled = bandTiersToEnabled(prefs.tiers);
    if (
      dailyCeiling !== prefs.daily_attention_ceiling_minutes ||
      quietStart !== prefs.quiet_hours.start ||
      quietEnd !== prefs.quiet_hours.end ||
      JSON.stringify(enabled) !== JSON.stringify(bandTiers)
    ) {
      setDailyCeiling(prefs.daily_attention_ceiling_minutes);
      setQuietStart(prefs.quiet_hours.start);
      setQuietEnd(prefs.quiet_hours.end);
      setBandTiers(enabled);
    }
  }

  const handleToggleBand = (bandId: string) => {
    setBandTiers((prev) => ({ ...prev, [bandId]: !prev[bandId] }));
  };

  const handleSave = () => {
    update.mutate(
      {
        tiers: enabledToBandTiers(bandTiers),
        quiet_hours: {
          start: quietStart,
          end: quietEnd,
          timezone: "Asia/Singapore",
        },
        daily_attention_ceiling_minutes: dailyCeiling,
      },
      {
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: NOTIF_KEY });
          setSaved(true);
          setTimeout(() => setSaved(false), 2000);
        },
      },
    );
  };

  if (isPending) {
    return (
      <div className={cn("space-y-6", className)}>
        <Skeleton variant="rect" className="h-24" />
        <Skeleton variant="rect" className="h-32" />
        <Skeleton variant="rect" className="h-16" />
      </div>
    );
  }

  return (
    <div className={cn("space-y-6", className)}>
      <div className="space-y-3">
        <div>
          <div className="flex justify-between mb-2">
            <label className="text-sm text-[var(--text-primary)]">
              Daily Attention Ceiling
            </label>
            <span className="text-sm font-mono text-[var(--text-secondary)]">
              {dailyCeiling} min
            </span>
          </div>
          <input
            type="range"
            min={5}
            max={120}
            step={5}
            value={dailyCeiling}
            onChange={(e) => setDailyCeiling(Number(e.target.value))}
            className="w-full h-2 rounded-full appearance-none bg-[var(--bg-elevated)] cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none
              [&::-webkit-slider-thumb]:w-4
              [&::-webkit-slider-thumb]:h-4
              [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:bg-[var(--accent-gold)]
              [&::-webkit-slider-thumb]:cursor-pointer"
          />
          <div className="flex justify-between text-xs text-[var(--text-muted)] mt-1">
            <span>5m</span>
            <span>2h</span>
          </div>
        </div>

        <p className="text-xs text-[var(--text-muted)]">
          Maximum daily decision-making time before throttling
        </p>
      </div>

      <div className="space-y-3">
        <p className="text-sm text-[var(--text-primary)]">
          Per-Band Notification Tiers
        </p>
        <div className="space-y-2">
          {BANDS.map((band) => (
            <div
              key={band.id}
              className="flex items-center justify-between rounded bg-[var(--bg-elevated)] p-3"
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: band.color }}
                />
                <span className="text-sm text-[var(--text-primary)]">
                  {band.label}
                </span>
              </div>
              <button
                onClick={() => handleToggleBand(band.id)}
                className={cn(
                  "relative w-10 h-5 rounded-full transition-colors",
                  bandTiers[band.id]
                    ? "bg-[var(--gain-green)]"
                    : "bg-[var(--bg-surface)] border border-[var(--border-default)]",
                )}
              >
                <span
                  className={cn(
                    "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform",
                    bandTiers[band.id] ? "left-5 translate-x-0" : "left-0.5",
                  )}
                />
              </button>
            </div>
          ))}
        </div>
        <p className="text-xs text-[var(--text-muted)]">
          Enable notifications to receive alerts when entering this regime band
        </p>
      </div>

      <div className="space-y-3">
        <p className="text-sm text-[var(--text-primary)]">Quiet Hours</p>
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <label className="text-xs text-[var(--text-muted)] block mb-1">
              Start
            </label>
            <input
              type="time"
              value={quietStart}
              onChange={(e) => setQuietStart(e.target.value)}
              className="w-full rounded border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1.5 text-sm text-[var(--text-primary)]"
            />
          </div>
          <div className="flex-1">
            <label className="text-xs text-[var(--text-muted)] block mb-1">
              End
            </label>
            <input
              type="time"
              value={quietEnd}
              onChange={(e) => setQuietEnd(e.target.value)}
              className="w-full rounded border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1.5 text-sm text-[var(--text-primary)]"
            />
          </div>
        </div>
        <p className="text-xs text-[var(--text-muted)]">
          No notifications during quiet hours except for Crisis alerts
        </p>
      </div>

      <button
        onClick={handleSave}
        disabled={update.isPending}
        className={cn(
          "px-4 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50",
          saved
            ? "bg-[var(--gain-green)] text-white"
            : "bg-[var(--accent-gold)] text-[var(--bg-base)] hover:brightness-110",
        )}
      >
        {saved ? "Saved!" : "Save Preferences"}
      </button>
    </div>
  );
}
