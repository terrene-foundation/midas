"use client";

import { useBriefs } from "@/lib/queries/useBriefs";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";
import { FileText, Clock, ChevronRight, Plus } from "lucide-react";

interface BriefListProps {
  onSelectBrief: (id: string) => void;
  selectedBriefId: string | null;
  onNewBrief: () => void;
}

export function BriefList({
  onSelectBrief,
  selectedBriefId,
  onNewBrief,
}: BriefListProps) {
  const { data, isPending } = useBriefs();

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-default)]">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">
          Briefs
        </h2>
        <button
          onClick={onNewBrief}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius)] text-xs font-medium bg-[var(--accent-gold)] text-black hover:brightness-110 transition-all"
        >
          <Plus size={14} />
          New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isPending ? (
          <div className="p-3 space-y-2">
            <BriefListItemSkeleton />
            <BriefListItemSkeleton />
            <BriefListItemSkeleton />
          </div>
        ) : data?.briefs.length === 0 ? (
          <div className="p-6 text-center">
            <FileText
              size={24}
              className="mx-auto mb-2 text-[var(--text-muted)]"
            />
            <p className="text-sm text-[var(--text-muted)]">No briefs yet</p>
            <button
              onClick={onNewBrief}
              className="mt-3 text-sm text-[var(--accent-gold)] hover:underline"
            >
              Create your first brief
            </button>
          </div>
        ) : (
          <div className="p-2">
            {data?.briefs.map((brief) => (
              <BriefListItem
                key={brief.id}
                brief={brief}
                isSelected={selectedBriefId === brief.id}
                onClick={() => onSelectBrief(brief.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface BriefListItemProps {
  brief: BriefSummary;
  isSelected: boolean;
  onClick: () => void;
}

function BriefListItem({ brief, isSelected, onClick }: BriefListItemProps) {
  const statusColors = {
    draft: "bg-[var(--text-muted)]",
    active: "bg-[var(--gain-green)]",
    archived: "bg-[var(--text-muted)]/50",
  };

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-[var(--radius)] p-3 mb-1.5 transition-all group",
        "border",
        isSelected
          ? "border-[var(--accent-gold)] bg-[var(--bg-hover)]"
          : "border-transparent hover:border-[var(--border-default)] hover:bg-[var(--bg-elevated)]",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                statusColors[brief.status as keyof typeof statusColors] ||
                  statusColors.draft,
              )}
            />
            <span className="text-sm font-medium text-[var(--text-primary)] truncate">
              {brief.title}
            </span>
          </div>
          {brief.hypothesis && (
            <p className="text-xs text-[var(--text-muted)] line-clamp-2 mb-1.5">
              {brief.hypothesis}
            </p>
          )}
          <div className="flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
            <span className="flex items-center gap-1">
              <Clock size={10} />v{brief.version}
            </span>
            <span>
              {new Date(brief.updated_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
            </span>
          </div>
        </div>
        <ChevronRight
          size={14}
          className={cn(
            "text-[var(--text-muted)] transition-transform",
            isSelected && "text-[var(--accent-gold)]",
          )}
        />
      </div>
    </button>
  );
}

function BriefListItemSkeleton() {
  return (
    <div className="rounded-[var(--radius)] p-3 border border-[var(--border-default)] bg-[var(--bg-surface)]">
      <div className="flex items-center gap-2 mb-2">
        <Skeleton className="w-1.5 h-1.5 rounded-full" />
        <Skeleton className="h-3.5 w-32" />
      </div>
      <Skeleton className="h-2.5 w-full mb-1.5" />
      <Skeleton className="h-2.5 w-2/3 mb-2" />
      <div className="flex gap-3">
        <Skeleton className="h-2 w-8" />
        <Skeleton className="h-2 w-12" />
      </div>
    </div>
  );
}
