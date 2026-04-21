import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AttentionBudgetGauge } from "@/elements/attention/AttentionBudgetGauge";

// Mock the React Query hook
const mockUseAttention = vi.fn();
vi.mock("@/lib/queries/usePulse", () => ({
  useAttention: () => mockUseAttention(),
}));

// Zustand store state that can be mutated between tests
const storeRef = {
  decisionSecondsToday: 0,
  fatigueSignal: false,
  dailyCeiling: null as number | null,
  setAttention: vi.fn(),
};

// Mock must handle both: useAttentionStore() (no arg) and useAttentionStore(selector)
vi.mock("@/stores/attention-store", () => ({
  useAttentionStore: (selector?: (s: typeof storeRef) => unknown) =>
    selector ? selector(storeRef) : storeRef,
}));

describe("AttentionBudgetGauge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeRef.decisionSecondsToday = 0;
    storeRef.fatigueSignal = false;
    storeRef.dailyCeiling = null;
    storeRef.setAttention = vi.fn();
    mockUseAttention.mockReturnValue({ data: null });
  });

  it("renders the Attn label", () => {
    render(<AttentionBudgetGauge />);
    expect(screen.getByText("Attn")).toBeInTheDocument();
  });

  it("shows 0m when no attention data and zero seconds", () => {
    render(<AttentionBudgetGauge />);
    expect(screen.getByText("0m")).toBeInTheDocument();
  });

  it("shows used minutes when store has decision seconds", () => {
    storeRef.decisionSecondsToday = 1200; // 20 minutes
    render(<AttentionBudgetGauge />);
    expect(screen.getByText("20m")).toBeInTheDocument();
  });

  it("rounds down to whole minutes", () => {
    storeRef.decisionSecondsToday = 90; // 1.5 minutes -> 1m
    render(<AttentionBudgetGauge />);
    expect(screen.getByText("1m")).toBeInTheDocument();
  });

  it("renders the gauge bar element", () => {
    const { container } = render(<AttentionBudgetGauge />);
    const bar = container.querySelector(
      '[class*="rounded-full"][class*="overflow-hidden"]',
    );
    expect(bar).toBeInTheDocument();
  });

  it("renders the fill bar inside the gauge", () => {
    const { container } = render(<AttentionBudgetGauge />);
    const fill = container.querySelector('[style*="width"]');
    expect(fill).toBeInTheDocument();
  });

  it("shows correct title attribute with minute counts", () => {
    storeRef.decisionSecondsToday = 600; // 10 min
    storeRef.dailyCeiling = 3600; // 60 min
    const { container } = render(<AttentionBudgetGauge />);
    const gauge = container.querySelector('[title*="Attention"]');
    expect(gauge).toHaveAttribute("title", "Attention: 10/60 min used");
  });

  it("calls setAttention when API data is available", () => {
    mockUseAttention.mockReturnValue({
      data: {
        decision_seconds_today: 900,
        fatigue_signal: true,
        a_t: 0.5,
        band: "elevated",
      },
    });
    render(<AttentionBudgetGauge />);
    expect(storeRef.setAttention).toHaveBeenCalledWith({
      decisionSecondsToday: 900,
      fatigueSignal: true,
      dailyCeiling: 3600,
    });
  });

  it("does not call setAttention when API data is null", () => {
    mockUseAttention.mockReturnValue({ data: null });
    render(<AttentionBudgetGauge />);
    expect(storeRef.setAttention).not.toHaveBeenCalled();
  });

  it("caps fill width at 100% when usage exceeds ceiling", () => {
    storeRef.decisionSecondsToday = 7200; // 120 min used
    storeRef.dailyCeiling = 3600; // 60 min ceiling
    const { container } = render(<AttentionBudgetGauge />);
    const fill = container.querySelector('[style*="width"]');
    // pct = min(1, 7200/3600) = 1.0 => 100%
    expect(fill).toHaveStyle({ width: "100%" });
  });

  it("passes custom className to the wrapper", () => {
    const { container } = render(
      <AttentionBudgetGauge className="extra-class" />,
    );
    expect(container.firstChild).toHaveClass("extra-class");
  });
});
