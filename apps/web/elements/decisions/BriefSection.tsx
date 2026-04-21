"use client";

import { cn } from "@/elements/ui/utils";

interface BriefSectionProps {
  title: string;
  content: string;
  type?: string;
  provenance?: {
    source?: string;
    confidence?: number;
    timestamp?: string;
  };
  className?: string;
}

/**
 * Renders a single section of a decision brief with provenance indicators.
 */
export function BriefSection({
  title,
  content,
  type,
  provenance,
  className,
}: BriefSectionProps) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-[var(--accent-gold)] uppercase tracking-wider">
          {title}
        </h3>
        {type && (
          <span className="text-[10px] text-[var(--text-muted)] px-1.5 py-0.5 rounded bg-[var(--bg-elevated)]">
            {type}
          </span>
        )}
      </div>
      <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
        {content}
      </p>
      {provenance && (
        <div className="flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
          {provenance.source && (
            <span className="flex items-center gap-1">
              <span className="w-1 h-1 rounded-full bg-[var(--text-muted)]" />
              {provenance.source}
            </span>
          )}
          {provenance.confidence !== undefined && (
            <span className="font-mono-nums">
              {Math.round(provenance.confidence * 100)}% conf
            </span>
          )}
          {provenance.timestamp && (
            <span>{new Date(provenance.timestamp).toLocaleDateString()}</span>
          )}
        </div>
      )}
    </div>
  );
}
