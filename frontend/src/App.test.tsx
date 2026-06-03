import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

describe("App Step 2 controls", () => {
  it("shows visualizer inspection controls without live supplier affordances", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ status: "ok" }), { status: 200 }))
    );

    render(<App />);

    expect(await screen.findByText("Gateway ok")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Schematic symbol style" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fit schematic" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Supplier")).not.toBeInTheDocument();
    expect(screen.queryByText("Octopart")).not.toBeInTheDocument();
  });
});
