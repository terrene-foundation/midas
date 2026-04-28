"use client";

import { useState } from "react";
import { useBriefVersions } from "@/lib/queries/useBriefs";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";
import { Clock, ChevronDown, ChevronUp } from "lucide-react";

interface BriefVersionHistoryProps {
  briefId: string;
  currentVersion: number;
  onRestoreVersion?: (version: number) => void;
}

export function BriefVersionHistory({
  briefId,
  currentVersion,
  onRestoreVersion,
}: BriefVersionHistoryProps) {
  const { data, isPending } = useBriefVersions(briefId);

  if (isPending) {
    return <BriefVersionHistorySkeleton />;
  }

  if (!data?.versions || data.versions.length === 0) {
    return (
      <div className="p-4 text-center">
        <p className="text-sm text-[var(--text-muted)]">
          No version history available
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider px-1">
        Version History
      </h3>
      <div className="space-y-1">
        {data.versions.map((version, index) => (
          <VersionItem
            key={version.version}
            version={version}
            isCurrent={version.version === currentVersion}
            isLatest={index === 0}
            onRestore={onRestoreVersion}
          />
        ))}
      </div>
    </div>
  );
}

interface VersionItemProps {
  version: {
    version: number;
    title: string;
    hypothesis: string;
    constraints: string;
    regime_assumptions: string;
    metrics: string;
    status: string;
    created_at: string;
  };
  isCurrent: boolean;
  isLatest: boolean;
  onRestore?: (version: number) => void;
}

function VersionItem({
  version,
  isCurrent,
  isLatest,
  onRestore,
}: VersionItemProps) {
  const [expanded, setExpanded] = useState(false);

  const statusColors = {
    draft: "bg-[var(--text-muted)]",
    active: "bg-[var(--gain-green)]",
    archived: "bg-[var(--text-muted)]/50",
  };

  return (
    <div
      className={cn(
        "rounded-[var(--radius)] border transition-colors",
        isCurrent
          ? "border-[var(--accent-gold)]/50 bg-[var(--accent-gold)]/5"
          : "border-[var(--border-default)] bg-[var(--bg-elevated)] hover:border-[var(--border-accent)]",
      )}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left"
      >
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              statusColors[version.status as keyof typeof statusColors] ||
                statusColors.draft,
            )}
          />
          <span className="text-sm font-medium text-[var(--text-primary)]">
            Version {version.version}
          </span>
          {isLatest && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--accent-gold)]/20 text-[var(--accent-gold)]">
              Latest
            </span>
          )}
          {isCurrent && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-hover)] text-[var(--text-muted)]">
              Current
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[var(--text-muted)]">
            {new Date(version.created_at).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </span>
          {expanded ? (
            <ChevronUp size={14} className="text-[var(--text-muted)]" />
          ) : (
            <ChevronDown size={14} className="text-[var(--text-muted)]" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 pt-1 border-t border-[var(--border-default)]/50">
          <div className="space-y-3 text-xs">
            <div>
              <span className="text-[var(--text-muted)]">Title: </span>
              <span className="text-[var(--text-secondary)]">
                {version.title || "Untitled"}
              </span>
            </div>
            {version.hypothesis && (
              <div>
                <span className="text-[var(--text-muted)]">Hypothesis: </span>
                <span className="text-[var(--text-secondary)] line-clamp-2">
                  {version.hypothesis}
                </span>
              </div>
            )}
            {version.constraints && (
              <div>
                <span className="text-[var(--text-muted)]">Constraints: </span>
                <span className="text-[var(--text-secondary)] line-clamp-2">
                  {version.constraints}
                </span>
              </div>
            )}
            {version.regime_assumptions && (
              <div>
                <span className="text-[var(--text-muted)]">Regime: </span>
                <span className="text-[var(--text-secondary)] line-clamp-2">
                  {version.regime_assumptions}
                </span>
              </div>
            )}
            {version.metrics && (
              <div>
                <span className="text-[var(--text-muted)]">Metrics: </span>
                <span className="text-[var(--text-secondary)] line-clamp-2">
                  {version.metrics}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function BriefVersionHistorySkeleton() {
  return (
    <div className="space-y-2 p-4">
      <Skeleton className="h-3 w-24" />
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="rounded-[var(--radius)] border border-[var(--border-default)] p-3"
          >
            <div className="flex items-center justify-between mb-2">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-16" />
            </div>
            <Skeleton className="h-2 w-full mb-1" />
            <Skeleton className="h-2 w-3/4" />
          </div>
        ))}
      </div>
    </div>
  );
}
