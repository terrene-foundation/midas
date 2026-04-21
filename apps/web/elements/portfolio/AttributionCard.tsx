"use client";

import { useAttribution } from "@/lib/queries/usePortfolio";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { GitMerge, Hand, Layers } from "lucide-react";

export function AttributionCard() {
  const { data, isPending } = useAttribution();

  if (isPending) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <p className="text-sm font-medium text-[var(--text-secondary)] mb-4">
          Brinson Attribution
        </p>
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!data?.factors?.length) {
    return (
      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
        <p className="text-sm font-medium text-[var(--text-secondary)] mb-3">
          Brinson Attribution
        </p>
        <p className="text-sm text-[var(--text-muted)] text-center py-4">
          No attribution data
        </p>
      </div>
    );
  }

  // Group factors into allocation, selection, interaction
  const allocation = data.factors.find(
    (f) =>
      f.name.toLowerCase().includes("allocation") ||
      f.name.toLowerCase().includes("alloc"),
  );
  const selection = data.factors.find(
    (f) =>
      f.name.toLowerCase().includes("selection") ||
      f.name.toLowerCase().includes("select"),
  );
  const interaction = data.factors.find(
    (f) =>
      f.name.toLowerCase().includes("interaction") ||
      f.name.toLowerCase().includes("interact"),
  );

  const rows: {
    label: string;
    value: number;
    icon: React.ReactNode;
    description: string;
  }[] = [
    {
      label: "Allocation Effect",
      value: allocation?.contribution ?? 0,
      icon: <GitMerge size={14} />,
      description: "Asset class tilts",
    },
    {
      label: "Selection Effect",
      value: selection?.contribution ?? 0,
      icon: <Hand size={14} />,
      description: "Security picking",
    },
    {
      label: "Interaction",
      value: interaction?.contribution ?? 0,
      icon: <Layers size={14} />,
      description: "Joint effect",
    },
  ];

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          Brinson Attribution
        </p>
        <FinancialFigure
          value={data.total_return * 100}
          format="percent"
          showSign
          className="text-xs"
        />
      </div>

      <div className="space-y-3">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between py-2 border-b border-[var(--border-default)] last:border-0"
          >
            <div className="flex items-center gap-2">
              <span className="text-[var(--text-muted)]">{row.icon}</span>
              <div>
                <p className="text-sm text-[var(--text-primary)]">
                  {row.label}
                </p>
                <p className="text-xs text-[var(--text-muted)]">
                  {row.description}
                </p>
              </div>
            </div>
            <FinancialFigure
              value={row.value * 100}
              format="percent"
              showSign
              className="text-sm"
            />
          </div>
        ))}
      </div>
    </div>
  );
}
