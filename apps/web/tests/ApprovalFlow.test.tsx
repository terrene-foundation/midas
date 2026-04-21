import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApprovalFlow } from "@/elements/decisions/ApprovalFlow";

// Mock the approve decision mutation
const mockMutate = vi.fn();
vi.mock("@/lib/queries/useDecisions", () => ({
  useApproveDecision: () => ({
    mutate: mockMutate,
  }),
}));

// Mock ReAuthModal to capture onResult callback
vi.mock("@/elements/ReAuthModal", () => ({
  ReAuthModal: ({
    open,
    onResult,
    reason,
  }: {
    open: boolean;
    onResult: (success: boolean) => void;
    reason?: string;
  }) => {
    if (!open) return null;
    return (
      <div data-testid="reauth-modal">
        <span>{reason}</span>
        <button onClick={() => onResult(true)} data-testid="reauth-success">
          ReAuth OK
        </button>
        <button onClick={() => onResult(false)} data-testid="reauth-fail">
          ReAuth Fail
        </button>
      </div>
    );
  },
}));

// Mock QuoteMovedDialog
vi.mock("@/elements/decisions/QuoteMovedDialog", () => ({
  QuoteMovedDialog: ({
    open,
    onProceedAtCurrent,
    onCancel,
  }: {
    open: boolean;
    onProceedAtCurrent: () => void;
    onSetLimit: () => void;
    onCancel: () => void;
    priceChangePct: number;
    band: string;
  }) => {
    if (!open) return null;
    return (
      <div data-testid="quote-moved-dialog">
        <button onClick={onProceedAtCurrent} data-testid="proceed-current">
          Proceed
        </button>
        <button onClick={onCancel} data-testid="quote-cancel">
          QCancel
        </button>
      </div>
    );
  },
}));

describe("ApprovalFlow", () => {
  const defaultProps = {
    decisionId: "decision-1",
    band: "calm" as const,
    isUrgentOrCrisis: false,
    needsReAuth: false,
    onApproved: vi.fn(),
    onCancel: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // Default: approve mutation succeeds
    mockMutate.mockImplementation(
      (_id: string, opts: { onSuccess?: () => void }) => {
        opts?.onSuccess?.();
      },
    );
  });

  it("renders the Approve button in idle state", () => {
    render(<ApprovalFlow {...defaultProps} />);
    expect(screen.getByText("Approve")).toBeInTheDocument();
  });

  it("submits approval directly when no re-auth required", async () => {
    const user = userEvent.setup();
    render(<ApprovalFlow {...defaultProps} />);
    await user.click(screen.getByText("Approve"));
    expect(mockMutate).toHaveBeenCalledWith("decision-1", expect.any(Object));
  });

  it("calls onApproved after successful direct approval", async () => {
    const user = userEvent.setup();
    render(<ApprovalFlow {...defaultProps} />);
    await user.click(screen.getByText("Approve"));
    expect(defaultProps.onApproved).toHaveBeenCalled();
  });

  it("shows Approved state after successful submission", async () => {
    const user = userEvent.setup();
    render(<ApprovalFlow {...defaultProps} />);
    await user.click(screen.getByText("Approve"));
    expect(screen.getByText(/Approved/)).toBeInTheDocument();
  });

  it("shows re-auth modal when isUrgentOrCrisis is true", async () => {
    const user = userEvent.setup();
    render(
      <ApprovalFlow {...defaultProps} isUrgentOrCrisis={true} band="crisis" />,
    );
    await user.click(screen.getByText("Approve"));
    expect(screen.getByTestId("reauth-modal")).toBeInTheDocument();
  });

  it("shows re-auth modal when needsReAuth is true", async () => {
    const user = userEvent.setup();
    render(<ApprovalFlow {...defaultProps} needsReAuth={true} />);
    await user.click(screen.getByText("Approve"));
    expect(screen.getByTestId("reauth-modal")).toBeInTheDocument();
  });

  it("passes correct reason to ReAuthModal", async () => {
    const user = userEvent.setup();
    render(
      <ApprovalFlow {...defaultProps} isUrgentOrCrisis={true} band="urgent" />,
    );
    await user.click(screen.getByText("Approve"));
    expect(
      screen.getByText("Approving urgent decision requires confirmation"),
    ).toBeInTheDocument();
  });

  it("submits approval after successful re-auth", async () => {
    const user = userEvent.setup();
    render(
      <ApprovalFlow {...defaultProps} isUrgentOrCrisis={true} band="urgent" />,
    );
    await user.click(screen.getByText("Approve"));
    await user.click(screen.getByTestId("reauth-success"));
    expect(mockMutate).toHaveBeenCalledWith("decision-1", expect.any(Object));
  });

  it("returns to idle on failed re-auth", async () => {
    const user = userEvent.setup();
    render(
      <ApprovalFlow {...defaultProps} isUrgentOrCrisis={true} band="urgent" />,
    );
    await user.click(screen.getByText("Approve"));
    await user.click(screen.getByTestId("reauth-fail"));
    // Modal closes, approve button returns
    expect(screen.getByText("Approve")).toBeInTheDocument();
    expect(screen.queryByTestId("reauth-modal")).not.toBeInTheDocument();
  });

  it("shows Submitting state while mutation is in flight", async () => {
    const user = userEvent.setup();
    // Hold the mutation open
    mockMutate.mockImplementation(() => {
      /* neither onSuccess nor onError called */
    });
    render(<ApprovalFlow {...defaultProps} />);
    await user.click(screen.getByText("Approve"));
    expect(screen.getByText("Submitting...")).toBeInTheDocument();
    expect(screen.getByText("Submitting...")).toBeDisabled();
  });

  it("returns to idle when mutation fails", async () => {
    const user = userEvent.setup();
    mockMutate.mockImplementation(
      (_id: string, opts: { onError?: () => void }) => {
        opts?.onError?.();
      },
    );
    render(<ApprovalFlow {...defaultProps} />);
    await user.click(screen.getByText("Approve"));
    // After error, approve button returns
    expect(screen.getByText("Approve")).toBeInTheDocument();
  });

  describe("quote moved detection", () => {
    it("shows quote moved dialog when price changes exceed threshold", async () => {
      const user = userEvent.setup();
      // Calm threshold is 0.5%, so 1% change should trigger
      render(
        <ApprovalFlow
          {...defaultProps}
          isUrgentOrCrisis={true}
          band="calm"
          currentPrice={101}
          briefPrice={100}
        />,
      );
      await user.click(screen.getByText("Approve"));
      await user.click(screen.getByTestId("reauth-success"));
      expect(screen.getByTestId("quote-moved-dialog")).toBeInTheDocument();
    });

    it("does not show quote moved when prices match", async () => {
      const user = userEvent.setup();
      render(
        <ApprovalFlow
          {...defaultProps}
          isUrgentOrCrisis={true}
          band="calm"
          currentPrice={100}
          briefPrice={100}
        />,
      );
      await user.click(screen.getByText("Approve"));
      await user.click(screen.getByTestId("reauth-success"));
      expect(
        screen.queryByTestId("quote-moved-dialog"),
      ).not.toBeInTheDocument();
      // Goes straight to submitting
      expect(mockMutate).toHaveBeenCalled();
    });

    it("submits when user proceeds at current price after quote moved", async () => {
      const user = userEvent.setup();
      render(
        <ApprovalFlow
          {...defaultProps}
          isUrgentOrCrisis={true}
          band="calm"
          currentPrice={101}
          briefPrice={100}
        />,
      );
      await user.click(screen.getByText("Approve"));
      await user.click(screen.getByTestId("reauth-success"));
      await user.click(screen.getByTestId("proceed-current"));
      expect(mockMutate).toHaveBeenCalledWith("decision-1", expect.any(Object));
    });
  });
});
