import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { BriefRenderer } from "@/elements/decisions/BriefRenderer";

const baseBrief = {
  decision_id: "d1",
  dollar_impact: 1000,
  card: {
    action_line: "Buy AAPL at $150",
    counter_evidence: "Earnings miss risk",
    what_would_change_mind: "If guidance cuts >10%",
    buttons: ["Approve", "Decline"],
  },
  sections: [
    { title: "Thesis", content: "Strong momentum", type: "bull" },
    { title: "Risk", content: "Macro headwinds", type: "bear" },
    { title: "Timing", content: "Earnings in 2 weeks", type: "timing" },
  ],
};

describe("BriefRenderer", () => {
  // Compressed density: low a_t, low dollar impact, high confidence
  const compressedProps = {
    brief: baseBrief,
    a_t: 0.1,
    band: "calm" as const,
    dollarImpact: 500,
    confidence: 0.95,
  };

  // Structured density: combinedScore ~0.38 (>= 0.3, < 0.5)
  // Formula: a_t*0.4 + min(dollarImpact/100000,1)*0.3 + (1-confidence)*0.3
  const structuredProps = {
    brief: baseBrief,
    a_t: 0.5,
    band: "elevated" as const,
    dollarImpact: 30000,
    confidence: 0.7,
  };

  // Full density: combinedScore ~0.58 (>= 0.5, < 0.7)
  const fullProps = {
    brief: baseBrief,
    a_t: 0.7,
    band: "urgent" as const,
    dollarImpact: 50000,
    confidence: 0.5,
  };

  // Extreme density: combinedScore ~0.90 (>= 0.7)
  const extremeProps = {
    brief: baseBrief,
    a_t: 0.9,
    band: "crisis" as const,
    dollarImpact: 100000,
    confidence: 0.2,
  };

  describe("compressed density", () => {
    it("shows action_line in compressed view", () => {
      render(<BriefRenderer {...compressedProps} />);
      expect(screen.getByText("Buy AAPL at $150")).toBeInTheDocument();
    });

    it("shows what_would_change_mind section", () => {
      render(<BriefRenderer {...compressedProps} />);
      expect(screen.getByText(/If guidance cuts/)).toBeInTheDocument();
    });

    it("shows 'Tap to expand' button", () => {
      render(<BriefRenderer {...compressedProps} />);
      expect(screen.getByText("Tap to expand full brief")).toBeInTheDocument();
    });

    it("expands to structured view on tap", async () => {
      const user = userEvent.setup();
      render(<BriefRenderer {...compressedProps} />);
      await user.click(screen.getByText("Tap to expand full brief"));
      // After expanding, section content from real BriefSection renders
      expect(screen.getByText("Strong momentum")).toBeInTheDocument();
      expect(screen.getByText("Macro headwinds")).toBeInTheDocument();
    });

    it("shows 'Brief' density badge", () => {
      render(<BriefRenderer {...compressedProps} />);
      expect(screen.getByText("Brief")).toBeInTheDocument();
    });
  });

  describe("structured density", () => {
    it("renders action_line and counter_evidence", () => {
      render(<BriefRenderer {...structuredProps} />);
      expect(screen.getByText("Buy AAPL at $150")).toBeInTheDocument();
      // Counter-evidence is rendered inline
      expect(
        screen.getByText(/Counter-evidence: Earnings miss risk/),
      ).toBeInTheDocument();
    });

    it("renders all section titles", () => {
      render(<BriefRenderer {...structuredProps} />);
      // BriefSection renders titles with CSS uppercase, DOM text stays original case
      expect(screen.getByText("Thesis")).toBeInTheDocument();
      expect(screen.getByText("Risk")).toBeInTheDocument();
      expect(screen.getByText("Timing")).toBeInTheDocument();
    });

    it("renders all section content", () => {
      render(<BriefRenderer {...structuredProps} />);
      expect(screen.getByText("Strong momentum")).toBeInTheDocument();
      expect(screen.getByText("Macro headwinds")).toBeInTheDocument();
      expect(screen.getByText("Earnings in 2 weeks")).toBeInTheDocument();
    });

    it("shows 'Standard' density badge", () => {
      render(<BriefRenderer {...structuredProps} />);
      expect(screen.getByText("Standard")).toBeInTheDocument();
    });
  });

  describe("full density", () => {
    it("shows Key Thesis header", () => {
      render(<BriefRenderer {...fullProps} />);
      expect(screen.getByText("Key Thesis")).toBeInTheDocument();
    });

    it("shows 'Detailed' density badge", () => {
      render(<BriefRenderer {...fullProps} />);
      // Both the header and the Key Thesis card render DensityBadge
      const badges = screen.getAllByText("Detailed");
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });

    it("renders calibration history when provided", () => {
      render(
        <BriefRenderer
          {...fullProps}
          calibrationHistory={[
            { date: "2026-04-01", calibration_error: 0.05 },
            { date: "2026-04-10", calibration_error: 0.15 },
          ]}
        />,
      );
      expect(screen.getByText("Calibration History")).toBeInTheDocument();
      expect(screen.getByText("5%")).toBeInTheDocument();
      expect(screen.getByText("15%")).toBeInTheDocument();
    });

    it("renders pool disagreement when provided", () => {
      render(<BriefRenderer {...fullProps} poolDisagreement={0.25} />);
      expect(screen.getByText("Pool Disagreement")).toBeInTheDocument();
      expect(screen.getByText("25%")).toBeInTheDocument();
    });

    it("does not render calibration history when empty", () => {
      render(<BriefRenderer {...fullProps} />);
      expect(screen.queryByText("Calibration History")).not.toBeInTheDocument();
    });
  });

  describe("extreme density", () => {
    it("renders HonestyBanner with reduced calibration warning", () => {
      render(<BriefRenderer {...extremeProps} oodScore={0.8} />);
      expect(
        screen.getByText("Reduced calibration in this state"),
      ).toBeInTheDocument();
    });

    it("shows 'Required Review Before Action' banner", () => {
      render(<BriefRenderer {...extremeProps} />);
      expect(
        screen.getByText("Required Review Before Action"),
      ).toBeInTheDocument();
    });

    it("shows review explanation text", () => {
      render(<BriefRenderer {...extremeProps} />);
      expect(
        screen.getByText(/requires explicit human review/),
      ).toBeInTheDocument();
    });

    it("shows 'Review Required' density badge", () => {
      render(<BriefRenderer {...extremeProps} />);
      expect(screen.getByText("Review Required")).toBeInTheDocument();
    });
  });

  describe("common behavior", () => {
    it("always renders confidence display", () => {
      render(<BriefRenderer {...compressedProps} />);
      // ConfidenceDistribution renders "95%" for confidence=0.95
      expect(screen.getByText("95%")).toBeInTheDocument();
    });

    it("passes custom className", () => {
      const { container } = render(
        <BriefRenderer {...compressedProps} className="my-custom" />,
      );
      expect(container.firstChild).toHaveClass("my-custom");
    });
  });
});
