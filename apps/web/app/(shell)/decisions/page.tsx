"use client";

import { useState } from "react";
import {
  useDecisions,
  useBrief,
  useApproveDecision,
  useDeclineDecision,
} from "@/lib/queries/useDecisions";
import { FinancialFigure } from "@/elements/FinancialFigure";
import { DecisionCardSkeleton } from "@/elements/LoadingSkeleton";
import { ReAuthModal } from "@/elements/ReAuthModal";
import { useRegimeStore } from "@/stores/regime-store";

export default function DecisionsPage() {
  const [status, setStatus] = useState<string>("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reAuthFor, setReAuthFor] = useState<string | null>(null);
  const { a_t } = useRegimeStore();
  const isUrgentOrCrisis = a_t >= 0.5;

  const { data: decisionsData, isPending } = useDecisions(status);
  const { data: brief } = useBrief(selectedId ?? "");
  const approve = useApproveDecision();
  const decline = useDeclineDecision();

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">
          Decisions
        </h1>
        <div className="flex gap-1 text-sm">
          {["pending", "approved", "declined"].map((s) => (
            <button
              key={s}
              onClick={() => {
                setStatus(s);
                setSelectedId(null);
              }}
              className={`px-3 py-1 rounded-[var(--radius)] transition-colors ${
                status === s
                  ? "bg-[var(--bg-hover)] text-[var(--accent-gold)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1 space-y-2">
          {isPending ? (
            <>
              <DecisionCardSkeleton />
              <DecisionCardSkeleton />
            </>
          ) : (
            (decisionsData?.decisions ?? []).map((d) => (
              <button
                key={d.id}
                onClick={() => setSelectedId(d.id)}
                className={`w-full text-left rounded-[var(--radius)] border p-3 transition-colors ${
                  selectedId === d.id
                    ? "border-[var(--accent-gold)] bg-[var(--bg-hover)]"
                    : "border-[var(--border-default)] bg-[var(--bg-surface)] hover:border-[var(--border-accent)]"
                }`}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">
                      {d.instruments || d.decision_type}
                    </p>
                    <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                      {d.action}
                    </p>
                  </div>
                  <FinancialFigure
                    value={d.confidence}
                    format="percent"
                    showSign={false}
                    className="text-xs"
                  />
                </div>
              </button>
            ))
          )}
        </div>

        <div className="lg:col-span-2">
          {selectedId && brief ? (
            <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-5 space-y-4">
              <div>
                <h2 className="text-base font-semibold text-[var(--text-primary)]">
                  Decision Brief
                </h2>
                <p className="text-sm text-[var(--text-secondary)] mt-1">
                  {brief.card.action_line}
                </p>
              </div>

              {brief.sections.length > 0 && (
                <div className="space-y-3">
                  {brief.sections.map((s, i) => (
                    <div key={i} className="space-y-1">
                      <h3 className="text-xs font-medium text-[var(--accent-gold)] uppercase tracking-wider">
                        {s.title}
                      </h3>
                      <p className="text-sm text-[var(--text-secondary)]">
                        {s.content}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {status === "pending" && (
                <div className="flex flex-col gap-3 pt-2 border-t border-[var(--border-default)]">
                  <button
                    onClick={() =>
                      isUrgentOrCrisis
                        ? setReAuthFor(selectedId)
                        : approve.mutate(selectedId)
                    }
                    className="w-full py-2.5 rounded-[var(--radius)] bg-[var(--gain-green)] text-white text-sm font-medium hover:brightness-110 transition-all"
                  >
                    Approve
                  </button>
                  <div className="flex justify-end">
                    <button
                      onClick={() => decline.mutate(selectedId)}
                      className="px-6 py-2 rounded-[var(--radius)] border border-[var(--loss-red)]/50 text-[var(--loss-red)] text-sm hover:bg-[var(--loss-red)]/10 transition-colors"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-[var(--radius)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-8 text-center">
              <p className="text-sm text-[var(--text-muted)]">
                Select a decision to view its brief
              </p>
            </div>
          )}
        </div>
      </div>

      <ReAuthModal
        open={!!reAuthFor}
        reason="Approving this decision requires confirmation"
        onResult={(ok) => {
          if (ok && reAuthFor) approve.mutate(reAuthFor);
          setReAuthFor(null);
        }}
      />
    </div>
  );
}
