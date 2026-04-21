"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

export function DataSourceStatus() {
  const { data, isPending } = useQuery({
    queryKey: ["settings-data-sources"],
    queryFn: () =>
      api.get<{
        sources: Array<{
          name: string;
          status: string;
          last_update: string | null;
        }>;
      }>("/settings/data-sources"),
  });

  if (isPending) {
    return <Skeleton variant="rect" className="h-32" />;
  }

  if (!data?.sources?.length) {
    return (
      <p className="text-sm text-[var(--text-muted)]">
        No data sources configured
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {data.sources.map((source, i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded bg-[var(--bg-elevated)] p-3"
        >
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "w-2 h-2 rounded-full",
                source.status === "healthy"
                  ? "bg-[var(--gain-green)]"
                  : source.status === "degraded"
                    ? "bg-[var(--regime-elevated)]"
                    : "bg-[var(--loss-red)]",
              )}
            />
            <span className="text-sm text-[var(--text-primary)]">
              {source.name}
            </span>
          </div>
          <div className="text-right">
            <p
              className={cn(
                "text-xs font-medium",
                source.status === "healthy"
                  ? "text-[var(--gain-green)]"
                  : source.status === "degraded"
                    ? "text-[var(--regime-elevated)]"
                    : "text-[var(--loss-red)]",
              )}
            >
              {source.status}
            </p>
            {source.last_update && (
              <p className="text-xs text-[var(--text-muted)]">
                {new Date(source.last_update).toLocaleTimeString()}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
