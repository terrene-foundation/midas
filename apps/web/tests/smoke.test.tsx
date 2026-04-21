import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

function Greeting({ name }: { name: string }) {
  return <div>Hello, {name}</div>;
}

describe("test framework smoke test", () => {
  it("renders a React component", () => {
    render(<Greeting name="Midas" />);
    expect(screen.getByText("Hello, Midas")).toBeInTheDocument();
  });

  it("asserts jest-dom matchers are available", () => {
    const container = document.createElement("div");
    container.textContent = "hello world";
    document.body.appendChild(container);
    expect(container).toHaveTextContent("hello world");
    document.body.removeChild(container);
  });
});
