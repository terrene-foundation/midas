"use client";

import { useState } from "react";
import {
  BriefList,
  BriefComposer,
  BriefVersionHistory,
} from "@/elements/briefs";
import { useBrief } from "@/lib/queries/useBriefs";

export default function BriefsPage() {
  const [selectedBriefId, setSelectedBriefId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showVersions, setShowVersions] = useState(false);

  const { data: selectedBrief } = useBrief(selectedBriefId ?? "");

  const handleSelectBrief = (id: string) => {
    setSelectedBriefId(id);
    setIsCreating(false);
    setShowVersions(false);
  };

  const handleNewBrief = () => {
    setSelectedBriefId(null);
    setIsCreating(true);
    setShowVersions(false);
  };

  const handleCloseComposer = () => {
    setIsCreating(false);
    if (selectedBriefId) {
      setShowVersions(true);
    }
  };

  const handleCancel = () => {
    setIsCreating(false);
    if (selectedBriefId) {
      setShowVersions(true);
    }
  };

  return (
    <div className="flex h-full">
      {/* Left Panel - Brief List */}
      <div className="w-80 border-r border-[var(--border-default)] bg-[var(--bg-surface)]">
        <BriefList
          onSelectBrief={handleSelectBrief}
          selectedBriefId={selectedBriefId}
          onNewBrief={handleNewBrief}
        />
      </div>

      {/* Center Panel - Composer or Detail */}
      <div className="flex-1">
        {isCreating ? (
          <BriefComposer
            onClose={handleCloseComposer}
            onCancel={handleCancel}
          />
        ) : selectedBriefId ? (
          <BriefComposer
            briefId={selectedBriefId}
            onClose={handleCloseComposer}
            onCancel={handleCancel}
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-sm text-[var(--text-muted)]">
                Select a brief to view or edit, or create a new one
              </p>
              <button
                onClick={handleNewBrief}
                className="mt-4 px-4 py-2 rounded-[var(--radius)] text-sm font-medium bg-[var(--accent-gold)] text-black hover:brightness-110 transition-all"
              >
                Create New Brief
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Right Panel - Version History */}
      {selectedBriefId && selectedBrief && !isCreating && (
        <div className="w-80 border-l border-[var(--border-default)] bg-[var(--bg-surface)] overflow-y-auto">
          <BriefVersionHistory
            briefId={selectedBriefId}
            currentVersion={selectedBrief.version}
          />
        </div>
      )}
    </div>
  );
}
