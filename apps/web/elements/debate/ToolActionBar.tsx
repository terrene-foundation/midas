"use client";

import { useState } from "react";
import { useInvokeTool } from "@/lib/queries/useDebate";
import { cn } from "@/elements/ui/utils";

interface ToolActionBarProps {
  threadId: string;
  currentDecision?: {
    decision_id?: string;
    current_allocation?: number;
  };
}

const TOOLS = [
  {
    id: "update-decision",
    label: "Update decision to X%",
    icon: "↗",
    requiresInput: true,
    inputLabel: "New allocation %",
    inputType: "number",
  },
  {
    id: "keep-at",
    label: "Keep at Y%",
    icon: "✓",
    requiresInput: true,
    inputLabel: "Allocation %",
    inputType: "number",
  },
  {
    id: "run-alt-backtest",
    label: "Run alt-backtest",
    icon: "⟳",
    requiresInput: false,
  },
  {
    id: "show-calibration-curve",
    label: "Show calibration curve",
    icon: "📈",
    requiresInput: false,
  },
  {
    id: "retrieve-analogues",
    label: "Retrieve analogues",
    icon: "🔍",
    requiresInput: false,
  },
  {
    id: "recompute-with-constraint",
    label: "Recompute with constraint",
    icon: "⚙",
    requiresInput: true,
    inputLabel: "Constraint",
    inputType: "text",
  },
  {
    id: "generate-counterfactual",
    label: "Generate counterfactual",
    icon: "⊃",
    requiresInput: false,
  },
  {
    id: "surface-override-pattern",
    label: "Surface override pattern",
    icon: "⚠",
    requiresInput: false,
  },
  {
    id: "query-fabric",
    label: "Query fabric",
    icon: "🕸",
    requiresInput: false,
  },
  {
    id: "query-head",
    label: "Query head",
    icon: "🤖",
    requiresInput: false,
  },
] as const;

export function ToolActionBar({
  threadId,
  currentDecision,
}: ToolActionBarProps) {
  const invokeTool = useInvokeTool();
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [toolInput, setToolInput] = useState("");

  const handleToolClick = (toolId: string) => {
    const tool = TOOLS.find((t) => t.id === toolId);
    if (!tool) return;

    if (tool.requiresInput) {
      setActiveTool(activeTool === toolId ? null : toolId);
      setToolInput("");
    } else {
      invokeTool.mutate({ threadId, toolName: toolId });
    }
  };

  const handleSubmitToolInput = () => {
    if (!activeTool) return;

    const tool = TOOLS.find((t) => t.id === activeTool);
    if (!tool) return;

    let params: Record<string, unknown> = {};

    if (activeTool === "update-decision" || activeTool === "keep-at") {
      params = { allocation: parseFloat(toolInput) };
    } else if (activeTool === "recompute-with-constraint") {
      params = { constraint: toolInput };
    }

    invokeTool.mutate(
      { threadId, toolName: activeTool, params },
      {
        onSuccess: () => {
          setActiveTool(null);
          setToolInput("");
        },
      },
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {TOOLS.map((tool) => (
          <button
            key={tool.id}
            onClick={() => handleToolClick(tool.id)}
            disabled={invokeTool.isPending}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium",
              "border transition-colors",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              activeTool === tool.id
                ? "border-[var(--accent-gold)] bg-[var(--accent-gold)]/10 text-[var(--accent-gold)]"
                : "border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-secondary)]",
              "hover:border-[var(--accent-gold)] hover:text-[var(--accent-gold)]",
            )}
          >
            <span>{tool.icon}</span>
            <span>{tool.label}</span>
          </button>
        ))}
      </div>

      {activeTool &&
        (() => {
          const tool = TOOLS.find((t) => t.id === activeTool);
          if (!tool?.requiresInput) return null;

          return (
            <div className="flex items-center gap-2 p-3 rounded bg-[var(--bg-elevated)] border border-[var(--border-default)]">
              <input
                type={tool.inputType}
                value={toolInput}
                onChange={(e) => setToolInput(e.target.value)}
                placeholder={tool.inputLabel}
                className="flex-1 rounded border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-1.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-gold)]"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleSubmitToolInput();
                  } else if (e.key === "Escape") {
                    setActiveTool(null);
                    setToolInput("");
                  }
                }}
              />
              <button
                onClick={handleSubmitToolInput}
                disabled={!toolInput || invokeTool.isPending}
                className="px-4 py-1.5 rounded bg-[var(--accent-gold)] text-[var(--bg-base)] text-sm font-medium disabled:opacity-50"
              >
                Run
              </button>
              <button
                onClick={() => {
                  setActiveTool(null);
                  setToolInput("");
                }}
                className="px-3 py-1.5 rounded text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                Cancel
              </button>
            </div>
          );
        })()}
    </div>
  );
}
