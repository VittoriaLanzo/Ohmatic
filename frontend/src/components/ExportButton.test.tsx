import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExportButton } from "./ExportButton";
import * as exportClient from "../features/export/exportClient";
import type { OhmaticCircuitV01 } from "../types/circuit";

const circuit: OhmaticCircuitV01 = {
  metadata: { title: "LED blinker", description: "", version: "0.1", tags: ["t"] },
  components: [{ id: "R1", type: "resistor", value: "10k", part: "0603", x: 0, y: 0, pins: { "1": "1", "2": "2" } }],
  nets: [{ name: "N1", pins: ["R1.1", "R1.2"] }]
};

afterEach(() => vi.restoreAllMocks());

describe("ExportButton", () => {
  it("is disabled until a circuit exists", () => {
    render(<ExportButton circuit={null} />);
    expect(screen.getByRole("button", { name: /export/i })).toBeDisabled();
  });

  it("opens the format menu and downloads the chosen format on click", async () => {
    const file = { filename: "led_blinker.zip", content_type: "application/zip", content: "UEsDBA==", encoding: "base64" as const };
    const exportSpy = vi.spyOn(exportClient, "exportCircuit").mockResolvedValue(file);
    const downloadSpy = vi.spyOn(exportClient, "downloadExport").mockImplementation(() => undefined);

    render(<ExportButton circuit={circuit} />);

    const trigger = screen.getByRole("button", { name: /export/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("menuitem", { name: /KiCad project/i }));

    await waitFor(() => expect(exportSpy).toHaveBeenCalledWith(circuit, "kicad_project"));
    await waitFor(() => expect(downloadSpy).toHaveBeenCalledWith(file));
    // Menu closes after a successful export.
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("exposes both KiCad formats", () => {
    render(<ExportButton circuit={circuit} />);
    fireEvent.click(screen.getByRole("button", { name: /export/i }));
    expect(screen.getByRole("menuitem", { name: /KiCad project/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Netlist/i })).toBeInTheDocument();
  });
});
