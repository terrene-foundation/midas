"use client";

import { useComplianceRules } from "@/lib/queries/useCompliance";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

export function ComplianceRuleViewer() {
  const { data: complianceData, isPending } = useComplianceRules();

  if (isPending) {
    return <Skeleton variant="rect" className="h-40" />;
  }

  if (!complianceData?.rules?.length) {
    return (
      <p className="text-sm text-[var(--text-muted)]">
        No compliance rules configured
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {complianceData.rules.map((rule) => (
        <div
          key={rule.id}
          className="rounded border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-2"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-[var(--text-primary)]">
                {rule.name}
              </span>
              <span
                className={cn(
                  "px-1.5 py-0.5 rounded text-xs",
                  rule.severity === "critical"
                    ? "bg-[var(--loss-red)]/20 text-[var(--loss-red)]"
                    : rule.severity === "warning"
                      ? "bg-[var(--regime-elevated)]/20 text-[var(--regime-elevated)]"
                      : "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
                )}
              >
                {rule.severity}
              </span>
            </div>
            <span
              className={cn(
                "text-xs font-medium",
                rule.status === "passing"
                  ? "text-[var(--gain-green)]"
                  : rule.status === "violated"
                    ? "text-[var(--loss-red)]"
                    : "text-[var(--text-muted)]",
              )}
            >
              {rule.status}
            </span>
          </div>
          <p className="text-xs text-[var(--text-secondary)]">
            {rule.description}
          </p>
        </div>
      ))}
    </div>
  );
}
