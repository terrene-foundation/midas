"use client";

import { useState } from "react";
import type { BriefResponse } from "@/lib/types";
import type { Band } from "@/stores/regime-store";
import { BriefSection } from "./BriefSection";
import { HonestyBanner } from "./HonestyBanner";
import { ConfidenceDistribution } from "./ConfidenceDistribution";
import { cn } from "@/elements/ui/utils";

interface BriefRendererProps {
  brief: BriefResponse;
  a_t: number;
  band: Band;
  dollarImpact: number;
  confidence: number;
  oodScore?: number;
  calibrationHistory?: Array<{
    date: string;
    calibration_error: number;
  }>;
  poolDisagreement?: number;
  className?: string;
}

type DensityLevel = "compressed" | "structured" | "full" | "extreme";

function deriveDensityLevel(
  a_t: number,
  dollarImpact: number,
  confidence: number,
): DensityLevel {
  // High attention band OR high dollar impact OR low confidence → higher density
  const attentionScore = a_t;
  const impactScore = Math.min(dollarImpact / 100000, 1); // Normalize $100k to 1
  const confidenceScore = 1 - confidence;

  const combinedScore =
    attentionScore * 0.4 + impactScore * 0.3 + confidenceScore * 0.3;

  if (combinedScore >= 0.7) return "extreme";
  if (combinedScore >= 0.5) return "full";
  if (combinedScore >= 0.3) return "structured";
  return "compressed";
}

interface DensityBadgeProps {
  level: DensityLevel;
}

function DensityBadge({ level }: DensityBadgeProps) {
  const config = {
    compressed: {
      label: "Brief",
      class: "text-[var(--text-muted)]",
    },
    structured: {
      label: "Standard",
      class: "text-[var(--text-secondary)]",
    },
    full: {
      label: "Detailed",
      class: "text-[var(--accent-gold)]",
    },
    extreme: {
      label: "Review Required",
      class: "text-[var(--loss-red)]",
    },
  };

  const { label, class: className } = config[level];

  return (
    <span
      className={cn(
        "text-[10px] font-medium px-2 py-0.5 rounded-full border",
        className,
      )}
    >
      {label}
    </span>
  );
}

/**
 * Renders brief at 4 density levels based on (a_t band × dollar impact × confidence tier).
 * - Compressed: thesis + key number + "what would change my mind" + tap-to-expand
 * - Structured: all 7 sections concise
 * - Full: structured + pinned summary card + calibration history + pool disagreement
 * - Extreme: full brief + honesty banner + required review before action
 */
export function BriefRenderer({
  brief,
  a_t,
  band,
  dollarImpact,
  confidence,
  oodScore = 0,
  calibrationHistory = [],
  poolDisagreement,
  className,
}: BriefRendererProps) {
  const [expanded, setExpanded] = useState(false);
  const [showFull, setShowFull] = useState(false);

  const densityLevel = deriveDensityLevel(a_t, dollarImpact, confidence);
  const isCompressed = densityLevel === "compressed";
  const isStructured = densityLevel === "structured";
  const isFull = densityLevel === "full";
  const isExtreme = densityLevel === "extreme";

  const renderCompressed = () => (
    <div className="space-y-3">
      <p className="text-sm text-[var(--text-primary)] font-medium">
        {brief.card.action_line}
      </p>
      {brief.card.what_would_change_mind && (
        <div className="p-3 rounded-[var(--radius)] bg-[var(--bg-elevated)] border-l-2 border-[var(--accent-gold)]">
          <p className="text-xs text-[var(--text-muted)] mb-1">
            What would change my mind:
          </p>
          <p className="text-sm text-[var(--text-secondary)]">
            {brief.card.what_would_change_mind}
          </p>
        </div>
      )}
      <button
        onClick={() => setExpanded(true)}
        className="text-xs text-[var(--accent-gold)] hover:underline"
      >
        Tap to expand full brief
      </button>
    </div>
  );

  const renderStructured = () => (
    <div className="space-y-4">
      <div className="p-3 rounded-[var(--radius)] bg-[var(--bg-elevated)]">
        <p className="text-sm text-[var(--text-primary)] font-medium">
          {brief.card.action_line}
        </p>
        {brief.card.counter_evidence && (
          <p className="text-xs text-[var(--text-secondary)] mt-2">
            Counter-evidence: {brief.card.counter_evidence}
          </p>
        )}
      </div>
      {brief.sections.map((section, i) => (
        <BriefSection key={i} title={section.title} content={section.content} />
      ))}
    </div>
  );

  const renderFull = () => (
    <div className="space-y-4">
      {/* Pinned summary card */}
      <div className="p-4 rounded-[var(--radius)] border border-[var(--accent-gold)]/30 bg-[var(--accent-gold)]/5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-[var(--accent-gold)]">
            Key Thesis
          </span>
          <DensityBadge level="full" />
        </div>
        <p className="text-sm text-[var(--text-primary)]">
          {brief.card.action_line}
        </p>
      </div>

      {/* All sections */}
      {brief.sections.map((section, i) => (
        <BriefSection key={i} title={section.title} content={section.content} />
      ))}

      {/* Calibration history */}
      {calibrationHistory.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
            Calibration History
          </h4>
          <div className="flex gap-2">
            {calibrationHistory.slice(0, 5).map((h, i) => (
              <div
                key={i}
                className="flex-1 p-2 rounded-[var(--radius)] bg-[var(--bg-elevated)] text-center"
              >
                <p className="text-[10px] text-[var(--text-muted)]">
                  {new Date(h.date).toLocaleDateString()}
                </p>
                <p
                  className={cn(
                    "text-xs font-mono-nums",
                    h.calibration_error < 0.1
                      ? "text-[var(--gain-green)]"
                      : h.calibration_error < 0.2
                        ? "text-[var(--accent-gold)]"
                        : "text-[var(--loss-red)]",
                  )}
                >
                  {Math.round(h.calibration_error * 100)}%
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pool disagreement */}
      {poolDisagreement !== undefined && (
        <div className="flex items-center justify-between p-3 rounded-[var(--radius)] bg-[var(--bg-elevated)]">
          <span className="text-xs text-[var(--text-muted)]">
            Pool Disagreement
          </span>
          <span
            className={cn(
              "text-sm font-mono-nums",
              poolDisagreement > 0.3
                ? "text-[var(--loss-red)]"
                : poolDisagreement > 0.15
                  ? "text-[var(--accent-gold)]"
                  : "text-[var(--gain-green)]",
            )}
          >
            {Math.round(poolDisagreement * 100)}%
          </span>
        </div>
      )}
    </div>
  );

  const renderExtreme = () => (
    <div className="space-y-4">
      <HonestyBanner oodScore={oodScore} />

      {renderFull()}

      {/* Required review banner */}
      <div className="p-4 rounded-[var(--radius)] border-2 border-[var(--loss-red)]/50 bg-[var(--loss-red)]/10">
        <div className="flex items-center gap-2">
          <span className="text-[var(--loss-red)]">🔒</span>
          <span className="text-sm font-medium text-[var(--loss-red)]">
            Required Review Before Action
          </span>
        </div>
        <p className="text-xs text-[var(--text-secondary)] mt-1">
          This decision requires explicit human review due to low model
          calibration in current market conditions. You must acknowledge the
          reduced reliability before proceeding.
        </p>
      </div>
    </div>
  );

  // Main render based on density level
  let content: React.ReactNode;
  switch (densityLevel) {
    case "compressed":
      content = expanded ? renderStructured() : renderCompressed();
      break;
    case "structured":
      content = renderStructured();
      break;
    case "full":
      content = renderFull();
      break;
    case "extreme":
      content = renderExtreme();
      break;
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/* Density indicator */}
      <div className="flex items-center justify-between">
        <ConfidenceDistribution
          confidence={confidence}
          className="flex-1 max-w-[200px]"
        />
        <DensityBadge level={densityLevel} />
      </div>

      {/* Content */}
      {content}
    </div>
  );
}
