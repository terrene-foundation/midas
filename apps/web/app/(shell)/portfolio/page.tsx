"use client";

import { useState } from "react";
import {
  PortfolioOverview,
  AllocationBars,
  AttributionCard,
  PositionList,
  PositionDetailSheet,
  RiskMetricsPanel,
} from "@/elements/portfolio";
import type { Position } from "@/lib/types";

export default function PortfolioPage() {
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(
    null,
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">
          Portfolio
        </h1>
      </div>

      {/* NAV hero + summary */}
      <PortfolioOverview />

      {/* Two-column: allocation + attribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AllocationBars />
        <AttributionCard />
      </div>

      {/* Risk metrics */}
      <RiskMetricsPanel />

      {/* Position list (sortable) */}
      <PositionList onPositionClick={setSelectedPosition} />

      {/* Position detail sheet */}
      <PositionDetailSheet
        position={selectedPosition}
        onClose={() => setSelectedPosition(null)}
      />
    </div>
  );
}
