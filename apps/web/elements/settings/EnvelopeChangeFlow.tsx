"use client";

import { useState } from "react";
import {
  useEnvelopeConfig,
  useUpdateEnvelope,
} from "@/lib/queries/useSettings";
import { ReAuthModal } from "@/elements/ReAuthModal";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

interface EnvelopeChangeFlowProps {
  onImpactBrief?: (config: {
    previousValues: Record<string, number>;
    newValues: Record<string, number>;
  }) => void;
}

export function EnvelopeChangeFlow({ onImpactBrief }: EnvelopeChangeFlowProps) {
  const { data: envelope, isPending } = useEnvelopeConfig();
  const updateEnvelope = useUpdateEnvelope();

  const [editing, setEditing] = useState(false);
  const [localValues, setLocalValues] = useState<Record<string, string>>({});
  const [showReAuth, setShowReAuth] = useState(false);
  const [pendingChange, setPendingChange] = useState<{
    isWidening: boolean;
    changes: Record<string, { from: number; to: number }>;
  } | null>(null);

  if (isPending) {
    return <Skeleton variant="rect" className="h-48" />;
  }

  if (!envelope) {
    return (
      <p className="text-sm text-[var(--text-muted)]">
        Failed to load envelope config
      </p>
    );
  }

  const isWidening = (field: string, newVal: number) => {
    const fieldMap: Record<string, number> = {
      drawdown_ceiling: envelope.drawdown_ceiling,
      vol_target_low: envelope.vol_target_low,
      vol_target_high: envelope.vol_target_high,
      concentration_cap: envelope.concentration_cap,
    };
    const current = fieldMap[field] ?? 0;
    // Widening means higher limits (less restrictive)
    return newVal > current;
  };

  const handleEdit = (field: string, value: string) => {
    setLocalValues((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = () => {
    const changes: Record<string, { from: number; to: number }> = {};
    let hasWidening = false;

    for (const [field, newValStr] of Object.entries(localValues)) {
      const newVal = parseFloat(newValStr);
      const fieldMap: Record<string, number> = {
        drawdown_ceiling: envelope.drawdown_ceiling,
        vol_target_low: envelope.vol_target_low,
        vol_target_high: envelope.vol_target_high,
        concentration_cap: envelope.concentration_cap,
      };
      const currentVal = fieldMap[field] ?? 0;
      if (!isNaN(newVal) && newVal !== currentVal) {
        changes[field] = { from: currentVal, to: newVal };
        if (isWidening(field, newVal)) {
          hasWidening = true;
        }
      }
    }

    if (Object.keys(changes).length === 0) {
      setEditing(false);
      setLocalValues({});
      return;
    }

    if (hasWidening) {
      // Show impact brief first, then re-auth
      onImpactBrief?.({
        previousValues: Object.fromEntries(
          Object.entries(changes).map(([k, v]) => [k, v.from]),
        ),
        newValues: Object.fromEntries(
          Object.entries(changes).map(([k, v]) => [k, v.to]),
        ),
      });
      setPendingChange({ isWidening: true, changes });
      setShowReAuth(true);
    } else {
      // Tightening - apply immediately with notification only
      applyChanges(changes);
    }
  };

  const applyChanges = (
    changes: Record<string, { from: number; to: number }>,
  ) => {
    const updates: Record<string, number> = {};
    for (const [field, { to }] of Object.entries(changes)) {
      updates[field] = to;
    }
    updateEnvelope.mutate(updates, {
      onSuccess: () => {
        setEditing(false);
        setLocalValues({});
        setPendingChange(null);
      },
    });
  };

  const handleReAuthResult = (success: boolean) => {
    setShowReAuth(false);
    if (success && pendingChange) {
      applyChanges(pendingChange.changes);
    }
    setPendingChange(null);
  };

  const renderField = (field: string, label: string, unit: string) => {
    const fieldMap: Record<string, number> = {
      drawdown_ceiling: envelope.drawdown_ceiling,
      vol_target_low: envelope.vol_target_low,
      vol_target_high: envelope.vol_target_high,
      concentration_cap: envelope.concentration_cap,
    };
    const currentVal = fieldMap[field] ?? 0;
    const displayVal = editing
      ? (localValues[field] ?? (currentVal * 100).toFixed(0))
      : (currentVal * 100).toFixed(0);

    return (
      <div key={field} className="space-y-1">
        <p className="text-xs text-[var(--text-muted)]">{label}</p>
        {editing ? (
          <input
            type="number"
            value={displayVal}
            onChange={(e) => handleEdit(field, e.target.value)}
            className="w-full rounded border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1 text-sm font-mono text-[var(--text-primary)]"
          />
        ) : (
          <p className="text-sm font-mono-nums tabular-nums text-[var(--text-primary)]">
            {displayVal}
            <span className="text-[var(--text-muted)] ml-1">{unit}</span>
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {renderField("drawdown_ceiling", "Drawdown Ceiling", "%")}
        {renderField("vol_target_low", "Vol Target Low", "%")}
        {renderField("vol_target_high", "Vol Target High", "%")}
        {renderField("concentration_cap", "Concentration Cap", "%")}
      </div>

      <div className="flex gap-3 pt-2">
        {editing ? (
          <>
            <button
              onClick={handleSave}
              disabled={updateEnvelope.isPending}
              className={cn(
                "px-4 py-2 rounded text-sm font-medium transition-colors",
                "bg-[var(--accent-gold)] text-[var(--bg-base)]",
                "disabled:opacity-50",
              )}
            >
              {updateEnvelope.isPending ? "Saving..." : "Apply Changes"}
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setLocalValues({});
              }}
              className="px-4 py-2 rounded text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="px-4 py-2 rounded text-sm font-medium border border-[var(--border-default)] text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
          >
            Edit Envelope
          </button>
        )}
      </div>

      <ReAuthModal
        open={showReAuth}
        onResult={handleReAuthResult}
        reason="Widening the envelope requires biometric verification"
      />
    </div>
  );
}
