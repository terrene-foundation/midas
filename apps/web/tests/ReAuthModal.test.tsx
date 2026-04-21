import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ReAuthModal } from "@/elements/ReAuthModal";

// Mock the API client
vi.mock("@/lib/api-client", () => ({
  api: {
    post: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  },
}));

import { api } from "@/lib/api-client";
const mockPost = vi.mocked(api.post);

describe("ReAuthModal", () => {
  const defaultProps = {
    open: true,
    onResult: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns null when open is false", () => {
    const { container } = render(
      <ReAuthModal {...defaultProps} open={false} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders the modal when open is true", () => {
    render(<ReAuthModal {...defaultProps} />);
    expect(screen.getByText("Confirm Action")).toBeInTheDocument();
  });

  it("renders the password input", () => {
    render(<ReAuthModal {...defaultProps} />);
    expect(
      screen.getByPlaceholderText("Enter password to confirm"),
    ).toBeInTheDocument();
  });

  it("renders Cancel and Confirm buttons", () => {
    render(<ReAuthModal {...defaultProps} />);
    expect(screen.getByText("Cancel")).toBeInTheDocument();
    expect(screen.getByText("Confirm")).toBeInTheDocument();
  });

  it("calls onResult(false) when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const onResult = vi.fn();
    render(<ReAuthModal {...defaultProps} onResult={onResult} />);
    await user.click(screen.getByText("Cancel"));
    expect(onResult).toHaveBeenCalledWith(false);
  });

  it("disables Confirm button when password is empty", () => {
    render(<ReAuthModal {...defaultProps} />);
    const confirmBtn = screen.getByText("Confirm");
    expect(confirmBtn).toBeDisabled();
  });

  it("enables Confirm button when password is entered", async () => {
    const user = userEvent.setup();
    render(<ReAuthModal {...defaultProps} />);
    const input = screen.getByPlaceholderText("Enter password to confirm");
    await user.type(input, "mypassword");
    const confirmBtn = screen.getByText("Confirm");
    expect(confirmBtn).not.toBeDisabled();
  });

  it("calls onResult(true) on successful re-auth", async () => {
    const user = userEvent.setup();
    const onResult = vi.fn();
    mockPost.mockResolvedValueOnce({});
    render(<ReAuthModal {...defaultProps} onResult={onResult} />);

    const input = screen.getByPlaceholderText("Enter password to confirm");
    await user.type(input, "correct-password");
    await user.click(screen.getByText("Confirm"));

    expect(mockPost).toHaveBeenCalledWith("/auth/reauth", {
      password: "correct-password",
    });
    // Wait for async to complete
    await vi.waitFor(() => {
      expect(onResult).toHaveBeenCalledWith(true);
    });
  });

  it("calls onResult(false) and shows error on 401", async () => {
    const user = userEvent.setup();
    const onResult = vi.fn();
    const { ApiError } = await import("@/lib/api-client");
    mockPost.mockRejectedValueOnce(new ApiError(401, "Unauthorized"));
    render(<ReAuthModal {...defaultProps} onResult={onResult} />);

    const input = screen.getByPlaceholderText("Enter password to confirm");
    await user.type(input, "wrong-password");
    await user.click(screen.getByText("Confirm"));

    await vi.waitFor(() => {
      expect(onResult).toHaveBeenCalledWith(false);
    });
    expect(
      screen.getByText("Incorrect password. Please try again."),
    ).toBeInTheDocument();
  });

  it("shows generic error on non-401 failure", async () => {
    const user = userEvent.setup();
    const { ApiError } = await import("@/lib/api-client");
    mockPost.mockRejectedValueOnce(new ApiError(500, "Server error"));
    render(<ReAuthModal {...defaultProps} />);

    const input = screen.getByPlaceholderText("Enter password to confirm");
    await user.type(input, "password");
    await user.click(screen.getByText("Confirm"));

    await vi.waitFor(() => {
      expect(
        screen.getByText("Verification failed. Please try again."),
      ).toBeInTheDocument();
    });
  });

  it("displays reason text when provided", () => {
    render(
      <ReAuthModal {...defaultProps} reason="Approving crisis decision" />,
    );
    expect(screen.getByText("Approving crisis decision")).toBeInTheDocument();
  });

  it("does not display reason text when not provided", () => {
    render(<ReAuthModal {...defaultProps} />);
    expect(
      screen.queryByText("Approving crisis decision"),
    ).not.toBeInTheDocument();
  });
});
