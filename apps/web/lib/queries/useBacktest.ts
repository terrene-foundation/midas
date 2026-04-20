import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  BacktestRun,
  BacktestResult,
  BacktestRegimeBreakdown,
  BacktestConsistency,
} from "@/lib/types";

export function useBacktestRuns() {
  return useQuery<{ runs: BacktestRun[] }>({
    queryKey: ["backtest-runs"],
    queryFn: () => api.get("/backtest/runs"),
  });
}

export function useBacktestResult(runId: string) {
  return useQuery<BacktestResult>({
    queryKey: ["backtest-result", runId],
    queryFn: () => api.get(`/backtest/results/${runId}`),
    enabled: !!runId,
  });
}

export function useBacktestRegimeBreakdown(runId: string) {
  return useQuery<BacktestRegimeBreakdown>({
    queryKey: ["backtest-regime-breakdown", runId],
    queryFn: () => api.get(`/backtest/${runId}/regime-breakdown`),
    enabled: !!runId,
  });
}

export function useBacktestConsistency(runId: string) {
  return useQuery<BacktestConsistency>({
    queryKey: ["backtest-consistency", runId],
    queryFn: () => api.get(`/backtest/${runId}/consistency`),
    enabled: !!runId,
  });
}
