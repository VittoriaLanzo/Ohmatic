import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { SchematicSvg } from "./SchematicSvg";
import { KNOWN_COMPONENT_TYPES, type OhmaticCircuitV01 } from "../types/circuit";
import { SCHEMATIC_SYMBOLS, type SymbolStyle } from "./schematic/symbols";

const brokenCircuit: OhmaticCircuitV01 = {
  metadata: {
    title: "Broken visual fixture",
    description: "Contains invalid pin refs",
    version: "0.1",
    tags: ["test"],
  },
  components: [
    {
      id: "Q1",
      type: "transistor_npn",
      value: "2N2222",
      part: "TO-92",
      x: 10,
      y: 10,
      pins: { B: "B", C: "C", E: "E" },
    },
    {
      id: "R1",
      type: "resistor",
      value: "1k",
      part: "0603",
      x: 80,
      y: 10,
      pins: { "1": "C", "2": "VCC" },
    },
  ],
  nets: [
    { name: "COLLECTOR", pins: ["Q1.C", "R1.1", "MISSING.1"] },
    { name: "BASE", pins: ["Q1.B", "Q1.NOPE"] },
  ],
};

const datasetExamples = JSON.parse(readFileSync(resolve(__dirname, "../../../dataset/examples.json"), "utf8")) as OhmaticCircuitV01[];

describe("SchematicSvg", () => {
  it("renders visible and accessible invalid-pin diagnostics", () => {
    render(<SchematicSvg circuit={brokenCircuit} phase="done" symbolStyle="ansi" />);

    expect(screen.getByRole("img", { name: "Broken visual fixture" })).toHaveAccessibleDescription(
      expect.stringContaining("unknown component MISSING.1")
    );
    expect(screen.getByText("Pin ref issue")).toBeInTheDocument();
    expect(document.querySelectorAll(".schematic-diagnostic-marker").length).toBeGreaterThanOrEqual(2);
  });

  it("uses explicit schematic symbols for known non-generic component types", () => {
    render(<SchematicSvg circuit={brokenCircuit} phase="done" symbolStyle="iec" />);

    expect(document.querySelector('[data-component-type="transistor_npn"] [data-symbol-kind="unknown"]')).toBeNull();
    expect(document.querySelector('[data-component-type="transistor_npn"] [data-symbol-mode="iec"]')).not.toBeNull();
    expect(document.querySelectorAll("[data-pin-anchor]").length).toBeGreaterThan(2);
  });

  it("uses component and net hover titles instead of one stale schematic title", () => {
    render(<SchematicSvg circuit={brokenCircuit} phase="done" symbolStyle="ansi" />);

    expect(screen.getByText("Q1 - transistor_npn - 2N2222")).toBeInTheDocument();
    expect(screen.getByText("Net COLLECTOR: Q1.C, R1.1")).toBeInTheDocument();
    expect(document.querySelector("svg > title")).toBeNull();
  });

  it("renders power symbols attached to their pin anchors", () => {
    const powerCircuit: OhmaticCircuitV01 = {
      metadata: {
        title: "Power attachment fixture",
        description: "Checks VCC and GND symbol attachment",
        version: "0.1",
        tags: ["test"],
      },
      components: [
        { id: "VCC1", type: "power_vcc", value: "5V", part: "VCC", x: 0, y: 0, pins: { "1": "VCC" } },
        { id: "R1", type: "resistor", value: "1k", part: "", x: 50, y: 0, pins: { "1": "VCC", "2": "GND" } },
        { id: "GND1", type: "power_gnd", value: "", part: "GND", x: 100, y: 0, pins: { "1": "GND" } },
      ],
      nets: [
        { name: "VCC", pins: ["VCC1.1", "R1.1"] },
        { name: "GND", pins: ["R1.2", "GND1.1"] },
      ],
    };

    render(<SchematicSvg circuit={powerCircuit} phase="done" symbolStyle="ansi" />);

    expect(document.querySelector('[data-component-type="power_vcc"] [data-symbol-kind="power_vcc:ansi"] path')).toHaveAttribute(
      "d",
      expect.stringContaining("M0 23")
    );
    expect(document.querySelector('[data-component-type="power_gnd"] [data-symbol-kind="power_gnd:ansi"] path')).toHaveAttribute(
      "d",
      expect.stringContaining("M0 -23")
    );
  });

  it("renders every known component type with real net routing and no unknown fallback", () => {
    for (const symbolStyle of ["ansi", "iec"] satisfies SymbolStyle[]) {
      const components = KNOWN_COMPONENT_TYPES.map((type, index) => ({
        id: `C${index + 1}`,
        type,
        value: type,
        part: "",
        x: (index % 12) * 24,
        y: Math.floor(index / 12) * 24,
        pins: Object.fromEntries(Object.keys(SCHEMATIC_SYMBOLS[type].anchors).map((pin) => [pin, pin])),
      }));
      const circuit: OhmaticCircuitV01 = {
        metadata: {
          title: `All ${symbolStyle} symbols`,
          description: "Renderer smoke test for every known component type",
          version: "0.1",
          tags: ["test"],
        },
        components,
        nets: [
          {
            name: "ALL_TYPES_BUS",
            pins: components.map((component) => `${component.id}.${Object.keys(component.pins)[0]}`),
          },
        ],
      };

      const { unmount } = render(<SchematicSvg circuit={circuit} phase="done" symbolStyle={symbolStyle} />);

      expect(document.querySelectorAll("[data-component-type]").length).toBe(KNOWN_COMPONENT_TYPES.length);
      expect(document.querySelector('[data-symbol-kind="unknown"]')).toBeNull();
      expect(document.querySelectorAll(".net-line").length).toBeGreaterThan(0);
      expect(screen.queryByText("Pin ref issue")).toBeNull();

      unmount();
    }
  });

  it("renders every checked-in dataset example, not only the mock circuit", () => {
    expect(datasetExamples.length).toBeGreaterThan(0);

    for (const circuit of datasetExamples) {
      const { unmount } = render(<SchematicSvg circuit={circuit} phase="done" symbolStyle="ansi" />);

      expect(screen.getByRole("img", { name: circuit.metadata.title })).toBeInTheDocument();
      expect(document.querySelectorAll("[data-component-type]").length).toBe(circuit.components.length);
      expect(document.querySelector('[data-symbol-kind="unknown"]')).toBeNull();
      expect(screen.queryByText("Pin ref issue")).toBeNull();

      unmount();
    }
  });
});
