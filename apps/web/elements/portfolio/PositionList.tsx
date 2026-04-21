"use client";

import { usePositions } from "@/lib/queries/usePortfolio";
import { PositionRow } from "./PositionRow";
import { PortfolioRowSkeleton } from "@/elements/LoadingSkeleton";
import { useState } from "react";
import { cn } from "@/elements/ui/utils";
import type { Position } from "@/lib/types";

type SortKey = "weight" | "unrealized_pnl" | "drift" | "market_value";
type SortDir = "asc" | "desc";

interface PositionListProps {
  onPositionClick?: (position: Position) => void;
}

export function PositionList({ onPositionClick }: PositionListProps) {
  const { data, isPending } = usePositions();
  const [sortKey, setSortKey] = useState<SortKey>("weight");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sorted = [...(data?.positions ?? [])].sort((a, b) => {
    let aVal: number, bVal: number;
    switch (sortKey) {
      case "weight":
        aVal = a.weight;
        bVal = b.weight;
        break;
      case "unrealized_pnl":
        aVal = a.unrealized_pnl;
        bVal = b.unrealized_pnl;
        break;
      case "drift":
        aVal = a.drift_from_target;
        bVal = b.drift_from_target;
        break;
      case "market_value":
        aVal = a.market_value;
        bVal = b.market_value;
        break;
    }
    return sortDir === "asc" ? aVal - bVal : bVal - aVal;
  });

  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--border-default)] flex items-center justify-between">
        <p className="text-sm font-medium text-[var(--text-secondary)]">
          Positions
        </p>
        <p className="text-xs text-[var(--text-muted)]">
          {data?.positions?.length ?? 0} positions
        </p>
      </div>

      {/* Sortable column headers */}
      <div className="px-4 py-2 border-b border-[var(--border-default)] bg-[var(--bg-elevated)]/50 hidden sm:flex">
        <div className="w-9 shrink-0" />
        <div className="w-[108px] shrink-0" />
        <div className="flex-1 flex justify-end min-w-[90px]">
          <SortHeader
            label="Market Value"
            sortKey="market_value"
            currentKey={sortKey}
            sortDir={sortDir}
            onClick={handleSort}
          />
        </div>
        <div className="w-[88px] shrink-0 text-right">
          <SortHeader
            label="P&L"
            sortKey="unrealized_pnl"
            currentKey={sortKey}
            sortDir={sortDir}
            onClick={handleSort}
          />
        </div>
        <div className="w-[68px] shrink-0 text-right hidden md:block">
          <SortHeader
            label="Weight"
            sortKey="weight"
            currentKey={sortKey}
            sortDir={sortDir}
            onClick={handleSort}
          />
        </div>
        <div className="w-[78px] shrink-0 text-right">
          <SortHeader
            label="Drift"
            sortKey="drift"
            currentKey={sortKey}
            sortDir={sortDir}
            onClick={handleSort}
          />
        </div>
        <div className="w-6 shrink-0" />
      </div>

      {/* Rows */}
      {isPending ? (
        <div className="divide-y divide-[var(--border-default)]">
          <PortfolioRowSkeleton />
          <PortfolioRowSkeleton />
          <PortfolioRowSkeleton />
        </div>
      ) : sorted.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)] text-center py-8">
          No positions
        </p>
      ) : (
        <div className="divide-y divide-[var(--border-default)]">
          {sorted.map((position) => (
            <PositionRow
              key={position.ticker}
              position={position}
              onClick={
                onPositionClick ? () => onPositionClick(position) : undefined
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SortHeader({
  label,
  sortKey,
  currentKey,
  sortDir,
  onClick,
}: {
  label: string;
  sortKey: SortKey;
  currentKey: SortKey;
  sortDir: SortDir;
  onClick: (key: SortKey) => void;
}) {
  const active = sortKey === currentKey;
  return (
    <button
      onClick={() => onClick(sortKey)}
      className={cn(
        "text-xs uppercase tracking-wider flex items-center gap-1 transition-colors",
        active
          ? "text-[var(--accent-gold)]"
          : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]",
      )}
    >
      {label}
      <span className="text-[10px]">
        {active ? (sortDir === "desc" ? "↓" : "↑") : "↕"}
      </span>
    </button>
  );
}
