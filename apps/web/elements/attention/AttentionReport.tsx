"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Skeleton } from "@/elements/LoadingSkeleton";
import { cn } from "@/elements/ui/utils";

interface AttentionReportProps {
  className?: string;
}

interface WeeklyData {
  day: string;
  date: string;
  decision_seconds: number;
  decision_count: number;
  avg_seconds_per_decision: number;
  override_rate: number;
}

interface WeeklySummary {
  total_decision_seconds: number;
  total_decision_count: number;
  avg_seconds_per_decision: number;
  avg_override_rate: number;
}

interface WeeklyResponse {
  days: WeeklyData[];
  summary: WeeklySummary;
}

function StatCard({
  label,
  value,
  subValue,
  accent = false,
}: {
  label: string;
  value: string;
  subValue?: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-3 space-y-1">
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p
        className={cn(
          "text-lg font-semibold font-mono-nums tabular-nums",
          accent ? "text-[var(--accent-gold)]" : "text-[var(--text-primary)]",
        )}
      >
        {value}
      </p>
      {subValue && (
        <p className="text-xs text-[var(--text-muted)]">{subValue}</p>
      )}
    </div>
  );
}

function BarChart({
  data,
  maxValue,
  formatFn,
}: {
  data: { label: string; value: number }[];
  maxValue: number;
  formatFn: (v: number) => string;
}) {
  if (maxValue === 0) {
    return (
      <div className="flex items-end gap-1 h-24">
        {data.map((d) => (
          <div
            key={d.label}
            className="flex-1 flex flex-col items-center gap-1"
          >
            <div className="w-full h-1 rounded bg-[var(--bg-elevated)]" />
            <span className="text-[9px] text-[var(--text-muted)]">
              {d.label}
            </span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-end gap-1 h-24">
      {data.map((d) => (
        <div key={d.label} className="flex-1 flex flex-col items-center gap-1">
          <span className="text-[9px] text-[var(--text-muted)] font-mono-nums">
            {formatFn(d.value)}
          </span>
          <div
            className="w-full rounded-t bg-[var(--accent-gold)]/70 hover:bg-[var(--accent-gold)] transition-colors"
            style={{ height: `${(d.value / maxValue) * 96}px` }}
            title={`${d.label}: ${formatFn(d.value)}`}
          />
          <span className="text-[9px] text-[var(--text-muted)]">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

export function AttentionReport({ className }: AttentionReportProps) {
  const [activeTab, setActiveTab] = useState<
    "time" | "volume" | "ttd" | "override"
  >("time");

  const { data: weeklyResponse, isPending } = useQuery<WeeklyResponse>({
    queryKey: ["attention-weekly"],
    queryFn: () => api.get("/pulse/attention/weekly"),
  });

  if (isPending) {
    return (
      <div className={cn("space-y-4", className)}>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} variant="rect" className="h-16" />
          ))}
        </div>
        <Skeleton variant="rect" className="h-40" />
      </div>
    );
  }

  const weeklyData = weeklyResponse?.days ?? [];
  const summary = weeklyResponse?.summary;

  const totalDecisionSeconds = summary?.total_decision_seconds ?? 0;
  const totalDecisionCount = summary?.total_decision_count ?? 0;
  const avgSecondsPerDecision = summary?.avg_seconds_per_decision ?? 0;
  const maxSeconds = Math.max(...weeklyData.map((d) => d.decision_seconds), 0);
  const maxCount = Math.max(...weeklyData.map((d) => d.decision_count), 0);
  const overrideRate = summary?.avg_override_rate ?? 0;

  const TABS = [
    { key: "time" as const, label: "Decision Time" },
    { key: "volume" as const, label: "Volume" },
    { key: "ttd" as const, label: "Time-to-Decide" },
    { key: "override" as const, label: "Override Rate" },
  ];

  return (
    <div className={cn("space-y-4", className)}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Total Decision Time"
          value={`${Math.round(totalDecisionSeconds / 60)}m`}
          subValue="this week"
          accent
        />
        <StatCard
          label="Decisions"
          value={String(totalDecisionCount)}
          subValue="this week"
        />
        <StatCard
          label="Avg Time/Decision"
          value={`${avgSecondsPerDecision.toFixed(1)}s`}
          subValue="deliberation"
        />
        <StatCard
          label="Override Rate"
          value={overrideRate > 0 ? `${(overrideRate * 100).toFixed(1)}%` : "—"}
          subValue="this week"
        />
      </div>

      <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4 space-y-3">
        <div className="flex gap-1 border-b border-[var(--border-default)]">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors",
                activeTab === tab.key
                  ? "border-[var(--accent-gold)] text-[var(--accent-gold)]"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "time" && (
          <BarChart
            data={weeklyData.map((d) => ({
              label: d.day,
              value: d.decision_seconds,
            }))}
            maxValue={maxSeconds}
            formatFn={(v) => (v >= 60 ? `${Math.round(v / 60)}m` : `${v}s`)}
          />
        )}

        {activeTab === "volume" && (
          <BarChart
            data={weeklyData.map((d) => ({
              label: d.day,
              value: d.decision_count,
            }))}
            maxValue={maxCount}
            formatFn={(v) => String(v)}
          />
        )}

        {activeTab === "ttd" && (
          <BarChart
            data={weeklyData.map((d) => ({
              label: d.day,
              value: d.avg_seconds_per_decision,
            }))}
            maxValue={Math.max(
              ...weeklyData.map((d) => d.avg_seconds_per_decision),
            )}
            formatFn={(v) => `${v.toFixed(1)}s`}
          />
        )}

        {activeTab === "override" && (
          <BarChart
            data={weeklyData.map((d) => ({
              label: d.day,
              value: d.override_rate,
            }))}
            maxValue={Math.max(
              ...weeklyData.map((d) => d.override_rate),
              0.01,
            )}
            formatFn={(v) => `${(v * 100).toFixed(1)}%`}
          />
        )}
      </div>
    </div>
  );
}
