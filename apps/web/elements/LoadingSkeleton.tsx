"use client";

import { cn } from "@/elements/ui/utils";

interface SkeletonProps {
  className?: string;
  variant?: "text" | "card" | "circle" | "rect";
}

export function Skeleton({ className, variant = "text" }: SkeletonProps) {
  return (
    <div
      className={cn(
        "skeleton-shimmer rounded-[var(--radius)]",
        variant === "text" && "h-4 w-3/4",
        variant === "card" && "h-24 w-full",
        variant === "circle" && "h-10 w-10 rounded-full",
        variant === "rect" && "h-12 w-full",
        className,
      )}
    />
  );
}

export function PulseSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-end justify-between">
        <div className="space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-10 w-48" />
        </div>
        <Skeleton className="h-16 w-48" variant="rect" />
      </div>
      <div className="space-y-2">
        <Skeleton variant="card" />
        <Skeleton variant="card" />
        <Skeleton variant="card" />
      </div>
    </div>
  );
}

export function DecisionCardSkeleton() {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
      <div className="flex justify-between">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-20" />
      </div>
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

export function PortfolioRowSkeleton() {
  return (
    <div className="flex items-center justify-between py-3 border-b border-[var(--border-default)]">
      <div className="flex items-center gap-3">
        <Skeleton variant="circle" />
        <Skeleton className="h-4 w-16" />
      </div>
      <div className="flex gap-6">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-16" />
      </div>
    </div>
  );
}

export function BacktestScorecardSkeleton() {
  return (
    <div className="grid grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="space-y-2 p-3 rounded-[var(--radius)] bg-[var(--bg-surface)]"
        >
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-6 w-20" />
        </div>
      ))}
    </div>
  );
}
