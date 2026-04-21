"use client";

import { useState } from "react";
import { cn } from "@/elements/ui/utils";

interface NotificationPreferencesProps {
  initialPreferences?: {
    daily_attention_ceiling?: number;
    band_tiers?: Record<string, boolean>;
    quiet_hours_start?: string;
    quiet_hours_end?: string;
  };
  onSave?: (prefs: {
    daily_attention_ceiling: number;
    band_tiers: Record<string, boolean>;
    quiet_hours_start: string;
    quiet_hours_end: string;
  }) => void;
}

const BANDS = [
  { id: "calm", label: "Calm", color: "var(--regime-calm)" },
  { id: "elevated", label: "Elevated", color: "var(--regime-elevated)" },
  { id: "urgent", label: "Urgent", color: "var(--regime-urgent)" },
  { id: "crisis", label: "Crisis", color: "var(--regime-crisis)" },
];

export function NotificationPreferences({
  initialPreferences = {},
  onSave,
}: NotificationPreferencesProps) {
  const [dailyCeiling, setDailyCeiling] = useState(
    initialPreferences.daily_attention_ceiling ?? 480,
  );
  const [bandTiers, setBandTiers] = useState<Record<string, boolean>>(
    initialPreferences.band_tiers ?? {
      calm: false,
      elevated: true,
      urgent: true,
      crisis: true,
    },
  );
  const [quietStart, setQuietStart] = useState(
    initialPreferences.quiet_hours_start ?? "22:00",
  );
  const [quietEnd, setQuietEnd] = useState(
    initialPreferences.quiet_hours_end ?? "07:00",
  );
  const [saved, setSaved] = useState(false);

  const handleToggleBand = (bandId: string) => {
    setBandTiers((prev) => ({ ...prev, [bandId]: !prev[bandId] }));
  };

  const handleSave = () => {
    onSave?.({
      daily_attention_ceiling: dailyCeiling,
      band_tiers: bandTiers,
      quiet_hours_start: quietStart,
      quiet_hours_end: quietEnd,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-6">
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
            min={60}
            max={960}
            step={30}
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
            <span>1h</span>
            <span>16h</span>
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
        className={cn(
          "px-4 py-2 rounded text-sm font-medium transition-colors",
          saved
            ? "bg-[var(--gain-green)] text-white"
            : "bg-[var(--accent-gold)] text-[var(--bg-base)]",
        )}
      >
        {saved ? "Saved!" : "Save Preferences"}
      </button>
    </div>
  );
}
