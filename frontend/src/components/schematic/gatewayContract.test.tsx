import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SchematicSvg } from "../SchematicSvg";
import { buildSchematicModel } from "./model";
import type { OhmaticCircuitV01 } from "../../types/circuit";

// Integration guard: the renderer must consume the gateway's `result.circuit` shape
// (gateway/stub/server.py _flatten) verbatim and stay crossing-free, in both symbol
// styles, including the layout-less case the gateway emits when STAGE_2_LAYOUT is
// absent (every component defaults to x=0, y=0).

// Exactly the gateway HARDCODED_CIRCUIT / _flatten shape.
const gatewayCircuit: OhmaticCircuitV01 = {
  metadata: { title: "Stub Circuit", description: "Hardcoded stub", version: "0.1", tags: ["stub"] },
  components: [
    { id: "R1", type: "resistor", value: "10kΩ", part: "0603", x: 50, y: 50, pins: { "1": "1", "2": "2" } },
    { id: "VCC1", type: "power_vcc", value: "5V", part: "VCC", x: 10, y: 10, pins: { "1": "1" } },
    { id: "GND1", type: "power_gnd", value: "", part: "GND", x: 90, y: 90, pins: { "1": "1" } },
  ],
  nets: [
    { name: "VCC", pins: ["VCC1.1", "R1.1"] },
    { name: "GND", pins: ["R1.2", "GND1.1"] },
  ],
};

// Layout-less gateway output: _flatten defaults x/y to 0 for every component.
const noLayoutCircuit: OhmaticCircuitV01 = {
  metadata: { title: "No layout", description: "", version: "0.1", tags: [] },
  components: ["U1", "R1", "R2", "C1", "D1"].map((id) => ({
    id,
    type: id.startsWith("U") ? "ic_opamp" : id.startsWith("C") ? "capacitor" : id.startsWith("D") ? "diode" : "resistor",
    value: "",
    part: "",
    x: 0,
    y: 0,
    pins: { "1": "1", "2": "2" },
  })),
  nets: [
    { name: "N1", pins: ["U1.1", "R1.1", "C1.1"] },
    { name: "N2", pins: ["R1.2", "R2.1", "D1.1"] },
    { name: "N3", pins: ["R2.2", "C1.2", "D1.2", "U1.2"] },
  ],
};

describe("gateway result.circuit renders through the schematic engine", () => {
  for (const style of ["ansi", "iec"] as const) {
    it(`renders the gateway stub circuit (${style}) with a dynamic canvas and animation hooks`, () => {
      const { container, unmount } = render(<SchematicSvg circuit={gatewayCircuit} phase="done" symbolStyle={style} />);
      const svg = container.querySelector("svg")!;

      // Canvas is sized to the circuit, not the old fixed 360x210 box.
      expect(svg.getAttribute("viewBox")).not.toBe("0 0 360 210");

      // Every component drew its real symbol (no unknown "?" fallback).
      expect(container.querySelectorAll("[data-component-type]").length).toBe(gatewayCircuit.components.length);
      expect(container.querySelector('[data-symbol-kind="unknown"]')).toBeNull();

      // Nets drew, and the draw-on animation hooks are present.
      expect(container.querySelectorAll(".net-line").length).toBeGreaterThan(0);
      const animated = container.querySelector(".net-line") as SVGElement | null;
      expect(animated?.getAttribute("style") ?? "").toContain("--draw-order");
      const component = container.querySelector(".schematic-component") as SVGElement | null;
      expect(component?.getAttribute("style") ?? "").toContain("--draw-order");
      unmount();
    });
  }

  it("renders a layout-less (all x=0,y=0) gateway response without stacking components", () => {
    const model = buildSchematicModel(noLayoutCircuit);
    const points = new Set(model.components.map((c) => `${Math.round(c.point.x)},${Math.round(c.point.y)}`));
    // Distinct grid cells despite identical input coordinates.
    expect(points.size).toBe(noLayoutCircuit.components.length);
    expect(model.diagnostics).toHaveLength(0);

    // And it still routes crossing-free.
    const seg = (d: string) => {
      const t = d.trim().split(/\s+/);
      const out: Array<[number, number, number, number]> = [];
      let x = 0;
      let y = 0;
      let i = 0;
      while (i < t.length) {
        const c = t[i++];
        if (c === "M") { x = +t[i++]; y = +t[i++]; }
        else if (c === "H") { const n = +t[i++]; out.push([x, y, n, y]); x = n; }
        else if (c === "V") { const n = +t[i++]; out.push([x, y, x, n]); y = n; }
      }
      return out;
    };
    const pts = new Map(model.components.map((c) => [c.id, c.point]));
    let crossings = 0;
    for (const route of model.routes) {
      const members = new Set(route.anchorRefs.map((ref) => ref.split(".")[0]));
      const segs = route.segments.flatMap(seg);
      for (const [id, p] of pts) {
        if (members.has(id)) continue;
        if (segs.some(([x1, y1, x2, y2]) => Math.max(x1, x2) >= p.x - 22 && Math.min(x1, x2) <= p.x + 22 && Math.max(y1, y2) >= p.y - 16 && Math.min(y1, y2) <= p.y + 16)) {
          crossings += 1;
        }
      }
    }
    expect(crossings).toBe(0);
  });
});
