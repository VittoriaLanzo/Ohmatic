import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResultPanels } from "./ResultPanels";
import type { GenerateResult } from "../types/api";

const resultWithPartsList = {
  circuit: {
    metadata: {
      title: "Parts",
      description: "Parts list test",
      version: "0.1",
      tags: ["parts"]
    },
    components: [
      {
        id: "VCC1",
        type: "power_vcc",
        value: "5V",
        part: "VCC",
        x: 0,
        y: 0,
        pins: { "1": "VCC" }
      },
      {
        id: "R1",
        type: "resistor",
        value: "10k",
        part: "0603",
        x: 10,
        y: 0,
        pins: { "1": "VCC", "2": "OUT" }
      }
    ],
    nets: [{ name: "VCC", pins: ["VCC1.1", "R1.1"] }]
  },
  drc_warnings: [],
  parts_list: [
    {
      id: "VCC1",
      type: "power_vcc",
      parts_list_part: "power_vcc",
      value: "5V",
      package: "VCC",
      description: "power_vcc 5V VCC",
      is_physical: false,
      buyable: false,
      match_status: "local_only"
    },
    {
      id: "R1",
      type: "resistor",
      parts_list_part: "resistor",
      value: "10k",
      package: "0603",
      description: "resistor 10k 0603",
      is_physical: true,
      buyable: true,
      match_status: "local_only"
    }
  ],
  latency_ms: { inference: 1, drc: 2, parts_list: 3 }
} as unknown as GenerateResult;

describe("ResultPanels parts list", () => {
  it("renders deterministic parts_list rows without supplier columns", () => {
    render(<ResultPanels result={resultWithPartsList} phase="done" />);

    fireEvent.click(screen.getByRole("tab", { name: /Parts/i }));

    expect(screen.getByText("VCC1")).toBeInTheDocument();
    expect(screen.getByText("R1")).toBeInTheDocument();
    expect(screen.getByText("not buyable")).toBeInTheDocument();
    expect(screen.getByText("buyable")).toBeInTheDocument();
    expect(screen.queryByText("MPN")).not.toBeInTheDocument();
    expect(screen.queryByText("Price")).not.toBeInTheDocument();
    expect(screen.queryByText("matched")).not.toBeInTheDocument();
    expect(screen.getByText("Parts 3ms")).toBeInTheDocument();
  });
});
