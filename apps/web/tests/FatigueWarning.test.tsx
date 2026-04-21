import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FatigueWarning } from "@/elements/attention/FatigueWarning";

// Zustand store state shared across the module mock
const storeRef = {
  fatigueSignal: false,
};

// Handle both selector and no-selector call patterns
vi.mock("@/stores/attention-store", () => ({
  useAttentionStore: (selector?: (s: typeof storeRef) => unknown) =>
    selector ? selector(storeRef) : storeRef,
}));

describe("FatigueWarning", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeRef.fatigueSignal = false;
  });

  it("returns null when fatigueSignal is false", () => {
    const { container } = render(<FatigueWarning />);
    expect(container.innerHTML).toBe("");
  });

  it("renders the warning when fatigueSignal is true", () => {
    storeRef.fatigueSignal = true;
    render(<FatigueWarning />);
    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
  });

  it("displays the rapid approval warning message", () => {
    storeRef.fatigueSignal = true;
    render(<FatigueWarning />);
    const boldEl = screen.getByText(
      "You are approving without reading the full brief.",
    );
    expect(boldEl).toBeInTheDocument();
  });

  it("displays the break suggestion text", () => {
    storeRef.fatigueSignal = true;
    render(<FatigueWarning />);
    expect(screen.getByText(/Consider taking a break/)).toBeInTheDocument();
  });

  it("displays the deliberation quality warning", () => {
    storeRef.fatigueSignal = true;
    render(<FatigueWarning />);
    expect(
      screen.getByText(/reduce the quality of oversight/),
    ).toBeInTheDocument();
  });

  it("marks the warning text as bold for the primary message", () => {
    storeRef.fatigueSignal = true;
    render(<FatigueWarning />);
    const boldEl = screen.getByText(
      "You are approving without reading the full brief.",
    );
    expect(boldEl.className).toContain("font-semibold");
  });

  it("passes custom className to the container", () => {
    storeRef.fatigueSignal = true;
    render(<FatigueWarning className="my-test-class" />);
    const alert = screen.getByRole("alert");
    expect(alert.className).toContain("my-test-class");
  });
});
