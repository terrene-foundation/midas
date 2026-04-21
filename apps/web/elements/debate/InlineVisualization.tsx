"use client";

import { cn } from "@/elements/ui/utils";

interface InlineVisualizationProps {
  data: {
    type: "chart" | "table" | "text";
    title?: string;
    chart?: {
      labels: string[];
      datasets: Array<{
        label: string;
        data: number[];
        color?: string;
      }>;
    };
    table?: {
      headers: string[];
      rows: Array<Array<string | number>>;
    };
    text?: string;
  };
}

export function InlineVisualization({ data }: InlineVisualizationProps) {
  if (data.type === "chart" && data.chart) {
    return <ChartVisualization chart={data.chart} title={data.title} />;
  }

  if (data.type === "table" && data.table) {
    return <TableVisualization table={data.table} title={data.title} />;
  }

  if (data.type === "text" && data.text) {
    return (
      <div className="rounded bg-[var(--bg-elevated)] p-4">
        {data.title && (
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">
            {data.title}
          </p>
        )}
        <pre className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap font-mono">
          {data.text}
        </pre>
      </div>
    );
  }

  return null;
}

function ChartVisualization({
  chart,
  title,
}: {
  chart: NonNullable<InlineVisualizationProps["data"]["chart"]>;
  title?: string;
}) {
  const maxValue = Math.max(...chart.datasets.flatMap((d) => d.data));

  return (
    <div className="rounded bg-[var(--bg-elevated)] p-4 space-y-3">
      {title && (
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
          {title}
        </p>
      )}
      <div className="space-y-2">
        {chart.datasets.map((dataset, i) => (
          <div key={i} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-[var(--text-secondary)]">
                {dataset.label}
              </span>
              {dataset.data.length === 1 && (
                <span className="font-mono text-[var(--text-primary)]">
                  {dataset.data[0].toFixed(2)}
                </span>
              )}
            </div>
            {dataset.data.length > 1 && (
              <div className="flex items-end gap-1 h-16">
                {dataset.data.map((value, j) => {
                  const height = maxValue > 0 ? (value / maxValue) * 100 : 0;
                  return (
                    <div
                      key={j}
                      className="flex-1 rounded-t relative group"
                      style={{
                        height: `${height}%`,
                        backgroundColor: dataset.color ?? "var(--accent-gold)",
                        minWidth: "8px",
                      }}
                    >
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 rounded bg-[var(--bg-surface)] text-xs text-[var(--text-primary)] opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                        {value.toFixed(2)}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
      {chart.labels.length > 1 && (
        <div className="flex justify-between text-xs text-[var(--text-muted)] pt-2 border-t border-[var(--border-default)]">
          {chart.labels.map((label, i) => (
            <span key={i} className="text-center">
              {label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function TableVisualization({
  table,
  title,
}: {
  table: NonNullable<InlineVisualizationProps["data"]["table"]>;
  title?: string;
}) {
  return (
    <div className="rounded bg-[var(--bg-elevated)] p-4 space-y-3">
      {title && (
        <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">
          {title}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-default)]">
              {table.headers.map((header, i) => (
                <th
                  key={i}
                  className="text-left py-2 px-2 text-xs text-[var(--text-muted)] font-medium"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-[var(--border-default)] last:border-0"
              >
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className={cn(
                      "py-2 px-2 font-mono text-[var(--text-primary)]",
                      j === 0 && "text-[var(--text-secondary)]",
                    )}
                  >
                    {typeof cell === "number" ? cell.toFixed(4) : cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
