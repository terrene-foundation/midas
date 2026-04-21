"use client";

import {
  useEnvelopeConfig,
  useUpdateEnvelope,
} from "@/lib/queries/useSettings";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

export function EnvelopeEditor() {
  const { data: envelope, isPending } = useEnvelopeConfig();
  const updateEnvelope = useUpdateEnvelope();

  if (isPending) {
    return (
      <div className="space-y-4">
        <Skeleton variant="rect" className="h-32" />
      </div>
    );
  }

  if (!envelope) {
    return (
      <p className="text-sm text-[var(--text-muted)]">
        Failed to load envelope config
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <EnvelopeField
          label="Drawdown Ceiling"
          value={(envelope.drawdown_ceiling * 100).toFixed(0)}
          unit="%"
          description="Maximum permitted drawdown from peak"
        />
        <EnvelopeField
          label="Vol Target Band"
          value={`${(envelope.vol_target_low * 100).toFixed(0)}% - ${(envelope.vol_target_high * 100).toFixed(0)}%`}
          description="Target annualized volatility range"
        />
        <EnvelopeField
          label="Concentration Cap"
          value={(envelope.concentration_cap * 100).toFixed(0)}
          unit="%"
          description="Maximum position size as % of portfolio"
        />
        <EnvelopeField
          label="Cost Budget Ceiling"
          value={(envelope.cost_budget_ceiling ?? 0).toFixed(4)}
          unit="bps"
          description="Maximum trading cost budget (basis points)"
        />
      </div>

      <div className="pt-2 border-t border-[var(--border-default)]">
        <p className="text-xs text-[var(--text-muted)] mb-2">
          Universe Exclusions
        </p>
        <div className="flex flex-wrap gap-2">
          {(envelope.universe_exclusions ?? []).length === 0 ? (
            <span className="text-sm text-[var(--text-muted)]">
              No exclusions configured
            </span>
          ) : (
            (envelope.universe_exclusions ?? []).map((ticker: string) => (
              <span
                key={ticker}
                className="inline-flex items-center px-2 py-1 rounded text-xs bg-[var(--bg-elevated)] text-[var(--text-secondary)]"
              >
                {ticker}
              </span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function EnvelopeField({
  label,
  value,
  unit,
  description,
}: {
  label: string;
  value: string;
  unit?: string;
  description?: string;
}) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className="text-sm font-mono-nums tabular-nums text-[var(--text-primary)]">
        {value}
        {unit && <span className="text-[var(--text-muted)] ml-1">{unit}</span>}
      </p>
      {description && (
        <p className="text-xs text-[var(--text-muted)]">{description}</p>
      )}
    </div>
  );
}
