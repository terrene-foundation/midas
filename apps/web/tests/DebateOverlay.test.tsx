import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DebateOverlay } from "@/elements/DebateOverlay";

// Mutable store ref -- tests mutate properties, mock closure always reads same object
const storeRef = {
  isOpen: false,
  context: null as { type: string; id: string } | null,
  closeDebate: vi.fn(),
};

// Handle both: useDebateOverlayStore() (destructure) and useDebateOverlayStore(selector)
vi.mock("@/stores/debate-overlay-store", () => ({
  useDebateOverlayStore: (selector?: (s: typeof storeRef) => unknown) =>
    selector ? selector(storeRef) : storeRef,
}));

// Mock the debate query hooks
const mockAddMessage = {
  mutate: vi.fn(),
  isPending: false,
};

vi.mock("@/lib/queries/useDebate", () => ({
  useDebateThread: (threadId: string) => ({
    data: threadId
      ? {
          thread_id: threadId,
          messages: [
            {
              id: "m1",
              content: "Bull thesis: strong earnings",
              severity: "bull",
              role: "agent",
            },
            {
              id: "m2",
              content: "Counter: macro risk",
              severity: "bear",
              role: "agent",
            },
          ],
          status: "active",
        }
      : undefined,
  }),
  useAddMessage: () => mockAddMessage,
}));

describe("DebateOverlay", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeRef.isOpen = false;
    storeRef.context = null;
    storeRef.closeDebate = vi.fn();
    mockAddMessage.mutate.mockImplementation(
      (_args: unknown, opts: { onSuccess?: () => void }) => {
        opts?.onSuccess?.();
      },
    );
  });

  it("returns null when overlay is not open", () => {
    storeRef.isOpen = false;
    const { container } = render(<DebateOverlay />);
    expect(container.innerHTML).toBe("");
  });

  it("renders the overlay panel when open", () => {
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "thread-123" };
    render(<DebateOverlay />);
    expect(screen.getByText("Debate — decision")).toBeInTheDocument();
  });

  it("renders debate header without type when context has no type", () => {
    storeRef.isOpen = true;
    storeRef.context = { type: "", id: "thread-123" };
    render(<DebateOverlay />);
    // When context.type is empty string, header shows "Debate — " (em-dash, then nothing)
    // testing-library normalizes trailing whitespace, so match with a regex
    const heading = screen.getByRole("heading", { level: 2 });
    expect(heading.textContent).toMatch(/^Debate\s*[—-]\s*$/);
  });

  it("renders existing thread messages", () => {
    storeRef.isOpen = true;
    storeRef.context = { type: "signal", id: "thread-123" };
    render(<DebateOverlay />);
    expect(
      screen.getByText("Bull thesis: strong earnings"),
    ).toBeInTheDocument();
    expect(screen.getByText("Counter: macro risk")).toBeInTheDocument();
  });

  it("shows 'No messages yet' when thread has no messages", () => {
    storeRef.isOpen = true;
    storeRef.context = { type: "signal", id: "" };
    render(<DebateOverlay />);
    expect(screen.getByText("No messages yet")).toBeInTheDocument();
  });

  it("renders the message input field", () => {
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "thread-123" };
    render(<DebateOverlay />);
    expect(
      screen.getByPlaceholderText("Type your argument..."),
    ).toBeInTheDocument();
  });

  it("renders the Send button", () => {
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "thread-123" };
    render(<DebateOverlay />);
    expect(screen.getByText("Send")).toBeInTheDocument();
  });

  it("disables Send button when message is empty", () => {
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "thread-123" };
    render(<DebateOverlay />);
    expect(screen.getByText("Send")).toBeDisabled();
  });

  it("enables Send button when message text is entered", async () => {
    const user = userEvent.setup();
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "thread-123" };
    render(<DebateOverlay />);
    const input = screen.getByPlaceholderText("Type your argument...");
    await user.type(input, "My counter-argument");
    expect(screen.getByText("Send")).not.toBeDisabled();
  });

  it("sends message on Send button click", async () => {
    const user = userEvent.setup();
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "thread-123" };
    render(<DebateOverlay />);
    const input = screen.getByPlaceholderText("Type your argument...");
    await user.type(input, "My counter-argument");
    await user.click(screen.getByText("Send"));
    expect(mockAddMessage.mutate).toHaveBeenCalledWith(
      { threadId: "thread-123", content: "My counter-argument" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("closes overlay when close button is clicked", async () => {
    const user = userEvent.setup();
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "thread-123" };
    render(<DebateOverlay />);
    await user.click(screen.getByLabelText("Close debate panel"));
    expect(storeRef.closeDebate).toHaveBeenCalled();
  });

  it("closes overlay when backdrop is clicked", async () => {
    const user = userEvent.setup();
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "thread-123" };
    render(<DebateOverlay />);
    // The backdrop is the absolute inset-0 div
    const backdrop = document.querySelector(".absolute.inset-0");
    expect(backdrop).toBeInTheDocument();
    await user.click(backdrop!);
    expect(storeRef.closeDebate).toHaveBeenCalled();
  });

  it("does not send when threadId is empty", async () => {
    const user = userEvent.setup();
    storeRef.isOpen = true;
    storeRef.context = { type: "decision", id: "" };
    render(<DebateOverlay />);
    const input = screen.getByPlaceholderText("Type your argument...");
    await user.type(input, "Some text");
    await user.click(screen.getByText("Send"));
    expect(mockAddMessage.mutate).not.toHaveBeenCalled();
  });
});
