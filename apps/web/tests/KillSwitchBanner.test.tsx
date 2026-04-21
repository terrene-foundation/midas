import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { KillSwitchBanner } from "@/elements/KillSwitchBanner";

// Mock the React Query hook
const mockUseKillSwitch = vi.fn();
vi.mock("@/lib/queries/useCompliance", () => ({
  useKillSwitch: () => mockUseKillSwitch(),
}));

describe("KillSwitchBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns null when kill switch is inactive", () => {
    mockUseKillSwitch.mockReturnValue({ data: { isActive: false } });
    const { container } = render(<KillSwitchBanner />);
    expect(container.innerHTML).toBe("");
  });

  it("returns null when kill switch data is undefined", () => {
    mockUseKillSwitch.mockReturnValue({ data: undefined });
    const { container } = render(<KillSwitchBanner />);
    expect(container.innerHTML).toBe("");
  });

  it("renders the banner with alert role when kill switch is active", () => {
    mockUseKillSwitch.mockReturnValue({
      data: { isActive: true, reason: "Manual activation" },
    });
    render(<KillSwitchBanner />);
    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
  });

  it("shows the trading paused message", () => {
    mockUseKillSwitch.mockReturnValue({
      data: { isActive: true },
    });
    render(<KillSwitchBanner />);
    expect(
      screen.getByText("Kill Switch Active — Trading Paused"),
    ).toBeInTheDocument();
  });

  it("shows a link to settings", () => {
    mockUseKillSwitch.mockReturnValue({
      data: { isActive: true },
    });
    render(<KillSwitchBanner />);
    const link = screen.getByText("View in Settings");
    expect(link).toBeInTheDocument();
    expect(link.closest("a")).toHaveAttribute("href", "/settings");
  });

  it("shows a pulsing indicator dot", () => {
    mockUseKillSwitch.mockReturnValue({
      data: { isActive: true },
    });
    render(<KillSwitchBanner />);
    const dot = document.querySelector(".animate-pulse");
    expect(dot).toBeInTheDocument();
  });
});
