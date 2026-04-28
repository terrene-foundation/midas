"use client";

import { useState, useEffect } from "react";
import {
  useUpdateBrief,
  useCreateBrief,
  useBrief,
} from "@/lib/queries/useBriefs";
import { cn } from "@/elements/ui/utils";
import { Save, Eye, Edit3, X } from "lucide-react";

interface BriefComposerProps {
  briefId: string | null;
  onClose?: () => void;
  onCancel?: () => void;
}

export function BriefComposer({
  briefId,
  onClose,
  onCancel,
}: BriefComposerProps) {
  const isNew = !briefId;
  const { data: existingBrief } = useBrief(briefId ?? "");
  const createBrief = useCreateBrief();
  const updateBrief = useUpdateBrief();

  const [title, setTitle] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [constraints, setConstraints] = useState("");
  const [regimeAssumptions, setRegimeAssumptions] = useState("");
  const [metrics, setMetrics] = useState("");
  const [status, setStatus] = useState("draft");
  const [isPreview, setIsPreview] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (existingBrief) {
      setTitle(existingBrief.title);
      setHypothesis(existingBrief.hypothesis);
      setConstraints(existingBrief.constraints);
      setRegimeAssumptions(existingBrief.regime_assumptions);
      setMetrics(existingBrief.metrics);
      setStatus(existingBrief.status);
    }
  }, [existingBrief]);

  const handleSave = async () => {
    if (!title.trim()) return;
    setIsSaving(true);

    const briefData = {
      title: title.trim(),
      hypothesis: hypothesis.trim(),
      constraints: constraints.trim(),
      regime_assumptions: regimeAssumptions.trim(),
      metrics: metrics.trim(),
      status,
    };

    try {
      if (isNew) {
        await createBrief.mutateAsync(briefData);
        onClose?.();
      } else if (briefId) {
        await updateBrief.mutateAsync({ id: briefId, data: briefData });
        onClose?.();
      }
    } finally {
      setIsSaving(false);
    }
  };

  const renderPreview = () => (
    <div className="prose prose-sm max-w-none space-y-4">
      <div>
        <h3 className="text-xs font-medium text-[var(--accent-gold)] uppercase tracking-wider mb-1">
          Hypothesis
        </h3>
        <p className="text-sm text-[var(--text-primary)]">
          {hypothesis || (
            <span className="text-[var(--text-muted)] italic">
              No hypothesis defined
            </span>
          )}
        </p>
      </div>

      <div>
        <h3 className="text-xs font-medium text-[var(--accent-gold)] uppercase tracking-wider mb-1">
          Constraints
        </h3>
        <p className="text-sm text-[var(--text-primary)]">
          {constraints || (
            <span className="text-[var(--text-muted)] italic">
              No constraints defined
            </span>
          )}
        </p>
      </div>

      <div>
        <h3 className="text-xs font-medium text-[var(--accent-gold)] uppercase tracking-wider mb-1">
          Regime Assumptions
        </h3>
        <p className="text-sm text-[var(--text-primary)]">
          {regimeAssumptions || (
            <span className="text-[var(--text-muted)] italic">
              No regime assumptions defined
            </span>
          )}
        </p>
      </div>

      <div>
        <h3 className="text-xs font-medium text-[var(--accent-gold)] uppercase tracking-wider mb-1">
          Metrics
        </h3>
        <p className="text-sm text-[var(--text-primary)]">
          {metrics || (
            <span className="text-[var(--text-muted)] italic">
              No metrics defined
            </span>
          )}
        </p>
      </div>
    </div>
  );

  const renderEditor = () => (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Title
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Brief title..."
          className="w-full px-3 py-2 rounded-[var(--radius)] bg-[var(--bg-elevated)] border border-[var(--border-default)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-gold)] transition-colors"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Hypothesis
        </label>
        <textarea
          value={hypothesis}
          onChange={(e) => setHypothesis(e.target.value)}
          placeholder="What is the investment thesis? What are you trying to prove?"
          rows={4}
          className="w-full px-3 py-2 rounded-[var(--radius)] bg-[var(--bg-elevated)] border border-[var(--border-default)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-gold)] transition-colors resize-none"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Constraints
        </label>
        <textarea
          value={constraints}
          onChange={(e) => setConstraints(e.target.value)}
          placeholder="What are the key constraints? Risk limits, budget, regulatory requirements..."
          rows={3}
          className="w-full px-3 py-2 rounded-[var(--radius)] bg-[var(--bg-elevated)] border border-[var(--border-default)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-gold)] transition-colors resize-none"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Regime Assumptions
        </label>
        <textarea
          value={regimeAssumptions}
          onChange={(e) => setRegimeAssumptions(e.target.value)}
          placeholder="What market regime assumptions is this based on? Bull market, high volatility, etc..."
          rows={3}
          className="w-full px-3 py-2 rounded-[var(--radius)] bg-[var(--bg-elevated)] border border-[var(--border-default)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-gold)] transition-colors resize-none"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Metrics
        </label>
        <textarea
          value={metrics}
          onChange={(e) => setMetrics(e.target.value)}
          placeholder="What metrics will you use to evaluate success? Sharpe ratio, max drawdown, etc..."
          rows={3}
          className="w-full px-3 py-2 rounded-[var(--radius)] bg-[var(--bg-elevated)] border border-[var(--border-default)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-gold)] transition-colors resize-none"
        />
      </div>

      <div className="space-y-1.5">
        <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Status
        </label>
        <div className="flex gap-2">
          {["draft", "active", "archived"].map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={cn(
                "px-3 py-1.5 rounded-[var(--radius)] text-xs font-medium transition-colors",
                status === s
                  ? "bg-[var(--accent-gold)] text-black"
                  : "bg-[var(--bg-elevated)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]",
              )}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-[var(--bg-surface)]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-default)]">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            {isNew
              ? "New Brief"
              : `Edit Brief v${existingBrief?.version ?? ""}`}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsPreview(!isPreview)}
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius)] text-xs transition-colors",
              isPreview
                ? "bg-[var(--bg-elevated)] text-[var(--accent-gold)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]",
            )}
          >
            {isPreview ? <Edit3 size={14} /> : <Eye size={14} />}
            {isPreview ? "Edit" : "Preview"}
          </button>
          {onCancel && (
            <button
              onClick={onCancel}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius)] text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {isPreview ? renderPreview() : renderEditor()}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-3 px-4 py-3 border-t border-[var(--border-default)]">
        {onCancel && (
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-[var(--radius)] text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
          >
            Cancel
          </button>
        )}
        <button
          onClick={handleSave}
          disabled={!title.trim() || isSaving}
          className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-[var(--radius)] text-sm font-medium transition-all",
            title.trim() && !isSaving
              ? "bg-[var(--accent-gold)] text-black hover:brightness-110"
              : "bg-[var(--accent-gold)]/50 text-black/50 cursor-not-allowed",
          )}
        >
          <Save size={14} />
          {isSaving ? "Saving..." : isNew ? "Create Brief" : "Save Version"}
        </button>
      </div>
    </div>
  );
}
