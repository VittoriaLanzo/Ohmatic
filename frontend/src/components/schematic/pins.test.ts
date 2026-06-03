import { describe, expect, it } from "vitest";
import type { OhmaticCircuitV01 } from "../../types/circuit";
import { buildSchematicModel } from "./model";

function circuit(overrides: Partial<OhmaticCircuitV01> = {}): OhmaticCircuitV01 {
  return {
    metadata: {
      title: "Bad pin fixture",
      description: "Exercises malformed refs",
      version: "0.1",
      tags: ["test"],
    },
    components: [
      {
        id: "U1",
        type: "ic_opamp",
        value: "LM358",
        part: "SOIC-8",
        x: 20,
        y: 20,
        pins: { "IN+": "A", "IN-": "B", OUT: "C", VCC: "VCC", GND: "GND" },
      },
      {
        id: "R1",
        type: "resistor",
        value: "10k",
        part: "0603",
        x: 80,
        y: 20,
        pins: { "1": "C", "2": "GND" },
      },
    ],
    nets: [
      { name: "BROKEN", pins: ["U1.OUT", "U1.NOPE", "R9.1", "not-a-pin-ref", "R1.1", "R1.1"] },
      { name: "FEEDBACK", pins: ["U1.OUT", "R1.1", "R1.2"] },
    ],
    ...overrides,
  };
}

describe("schematic model pin handling", () => {
  it("surfaces invalid pin refs as visible and accessible diagnostics", () => {
    const model = buildSchematicModel(circuit());

    expect(model.diagnostics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ ref: "U1.NOPE", kind: "unknown_pin", visible: true }),
        expect.objectContaining({ ref: "R9.1", kind: "unknown_component", visible: true }),
        expect.objectContaining({ ref: "not-a-pin-ref", kind: "malformed_ref", visible: true }),
        expect.objectContaining({ ref: "R1.1", kind: "duplicate_ref", visible: true }),
      ])
    );
    expect(model.accessibleDiagnostics).toContain("unknown pin U1.NOPE");
    expect(model.accessibleDiagnostics).toContain("unknown component R9.1");
    expect(model.accessibleDiagnostics).toContain("malformed pin ref not-a-pin-ref");
  });

  it("routes multi-pin nets from pin anchors instead of component centers", () => {
    const model = buildSchematicModel(circuit());
    const feedback = model.routes.find((route) => route.name === "FEEDBACK");

    expect(feedback?.kind).toBe("bus");
    expect(feedback?.segments.length).toBeGreaterThanOrEqual(3);
    expect(new Set(feedback?.anchorRefs).size).toBe(3);

    const opamp = model.components.find((component) => component.id === "U1");
    expect(opamp?.anchors["IN+"].x).not.toBe(opamp?.anchors.OUT.x);
    expect(opamp?.anchors["IN+"].y).not.toBe(opamp?.anchors["IN-"].y);
  });

  it("orients common pin names to the expected schematic sides", () => {
    const model = buildSchematicModel({
      metadata: {
        title: "Orientation fixture",
        description: "Checks deterministic pin anchors",
        version: "0.1",
        tags: ["test"],
      },
      components: [
        { id: "VCC1", type: "power_vcc", value: "5V", part: "VCC", x: 0, y: 0, pins: { "1": "VCC" } },
        { id: "GND1", type: "power_gnd", value: "", part: "GND", x: 20, y: 0, pins: { "1": "GND" } },
        { id: "D1", type: "diode", value: "", part: "", x: 40, y: 0, pins: { A: "A", K: "K" } },
        { id: "Q1", type: "transistor_npn", value: "", part: "", x: 60, y: 0, pins: { B: "B", C: "C", E: "E" } },
        { id: "U1", type: "ic_opamp", value: "", part: "", x: 80, y: 0, pins: { "IN+": "P", "IN-": "N", OUT: "O", VCC: "V", GND: "G" } },
      ],
      nets: [
        { name: "VCC", pins: ["VCC1.1", "U1.VCC"] },
        { name: "GND", pins: ["GND1.1", "U1.GND"] },
        { name: "DIODE", pins: ["D1.A", "D1.K"] },
        { name: "BJT", pins: ["Q1.B", "Q1.C", "Q1.E"] },
        { name: "OPAMP", pins: ["U1.IN+", "U1.IN-", "U1.OUT"] },
      ],
    });

    const byId = new Map(model.components.map((component) => [component.id, component]));
    const vcc = byId.get("VCC1")!;
    const gnd = byId.get("GND1")!;
    const diode = byId.get("D1")!;
    const transistor = byId.get("Q1")!;
    const opamp = byId.get("U1")!;

    expect(vcc.anchors["1"].y).toBeGreaterThan(vcc.point.y);
    expect(gnd.anchors["1"].y).toBeLessThan(gnd.point.y);
    expect(diode.anchors.A.x).toBeLessThan(diode.point.x);
    expect(diode.anchors.K.x).toBeGreaterThan(diode.point.x);
    expect(transistor.anchors.B.x).toBeLessThan(transistor.point.x);
    expect(transistor.anchors.C.y).toBeLessThan(transistor.point.y);
    expect(transistor.anchors.E.y).toBeGreaterThan(transistor.point.y);
    expect(opamp.anchors["IN-"].y).toBeLessThan(opamp.anchors["IN+"].y);
    expect(opamp.anchors.OUT.x).toBeGreaterThan(opamp.point.x);
  });
});
