import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { KNOWN_COMPONENT_TYPES, type OhmaticCircuitV01 } from "../../types/circuit";
import { SCHEMATIC_SYMBOLS } from "./symbols";
import { buildSchematicModel } from "./model";

// Two pins that resolve to the same anchor point stack two different nets at one
// place: the multi-net rendering defect. These guard the model so a new symbol or
// a regression can't reintroduce an overlap.

// Documented aliases: alternative names (letter vs numeric) for the SAME physical
// terminal, never both present in one netlist, so they intentionally share a side.
const ALIAS_GROUPS: Partial<Record<string, string[][]>> = {
  potentiometer: [["1", "A"], ["2", "B"]],
  battery: [["1", "+"], ["2", "-"]],
};

const sameSet = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join() === [...b].sort().join();
const ptKey = (p: { x: number; y: number }) => `${Math.round(p.x * 10) / 10},${Math.round(p.y * 10) / 10}`;

const dataset = JSON.parse(
  readFileSync(resolve(__dirname, "../../../../dataset/examples.json"), "utf8")
) as OhmaticCircuitV01[];

const circuit = (components: OhmaticCircuitV01["components"], nets: OhmaticCircuitV01["nets"] = []): OhmaticCircuitV01 => ({
  metadata: { title: "t", description: "", version: "0.1", tags: [] },
  components,
  nets,
});

describe("anchor integrity (multi-net overlap guards)", () => {
  it("no symbol maps two non-alias pins to the same side", () => {
    const offenders: string[] = [];
    for (const type of KNOWN_COMPONENT_TYPES) {
      const bySpec = new Map<string, string[]>();
      for (const [pin, spec] of Object.entries(SCHEMATIC_SYMBOLS[type].anchors)) {
        bySpec.set(spec, [...(bySpec.get(spec) ?? []), pin]);
      }
      for (const pins of bySpec.values()) {
        if (pins.length < 2) continue;
        const allowed = (ALIAS_GROUPS[type] ?? []).some((group) => sameSet(group, pins));
        if (!allowed) offenders.push(`${type}: [${pins.join(", ")}]`);
      }
    }
    expect(offenders, `pins sharing a side: ${offenders.join(" | ")}`).toHaveLength(0);
  });

  it("op-amp VEE/GND and sensor OUT/SIG resolve to distinct anchors", () => {
    for (const [type, pins] of [["ic_opamp", ["VEE", "GND"]], ["sensor", ["OUT", "SIG"]]] as const) {
      const a = SCHEMATIC_SYMBOLS[type].anchors;
      expect(a[pins[0]], `${type} ${pins[0]} vs ${pins[1]}`).not.toBe(a[pins[1]]);
    }
  });

  it("distributes unmapped pins to distinct anchors for 1..40 pins", () => {
    for (let n = 1; n <= 40; n += 1) {
      const pins = Object.fromEntries(Array.from({ length: n }, (_, i) => [`z${i}`, `${i}`]));
      const model = buildSchematicModel(circuit([{ id: "U1", type: "resistor", value: "", part: "", x: 0, y: 0, pins }]));
      const anchors = Object.values(model.components[0].anchors).map(ptKey);
      expect(new Set(anchors).size, `n=${n}`).toBe(n);
    }
  });

  it("never lets an unmapped pin land on a mapped pin's anchor", () => {
    // thyristor_scr/triac/servo/microphone have a mapped right-side pin that the
    // positional fallback used to overwrite; check the avoidance across all types.
    for (const type of KNOWN_COMPONENT_TYPES) {
      const mapped = Object.keys(SCHEMATIC_SYMBOLS[type].anchors);
      const pins = Object.fromEntries([...mapped, "X1", "X2"].map((p) => [p, p]));
      const model = buildSchematicModel(circuit([{ id: "U1", type, value: "", part: "", x: 0, y: 0, pins }]));
      const anchors = model.components[0].anchors;
      const used = new Set(mapped.flatMap((p) => (ALIAS_GROUPS[type] ? [] : [ptKey(anchors[p])])));
      for (const extra of ["X1", "X2"]) {
        if (ALIAS_GROUPS[type]) continue; // alias maps intentionally collide; skip
        expect(used.has(ptKey(anchors[extra])), `${type} ${extra} overlaps a mapped pin`).toBe(false);
      }
    }
  });

  it("gives every used pin a distinct anchor across all dataset examples", () => {
    const collisions: string[] = [];
    for (const example of dataset) {
      const model = buildSchematicModel(example);
      const byId = new Map(model.components.map((c) => [c.id, c]));
      const usedPins = new Map<string, Set<string>>();
      for (const net of example.nets) {
        for (const ref of net.pins) {
          const dot = ref.indexOf(".");
          if (dot < 0) continue;
          const [id, pin] = [ref.slice(0, dot), ref.slice(dot + 1)];
          usedPins.set(id, (usedPins.get(id) ?? new Set()).add(pin));
        }
      }
      for (const [id, pins] of usedPins) {
        const comp = byId.get(id);
        if (!comp) continue;
        const points = [...pins].map((p) => comp.anchors[p]).filter(Boolean).map(ptKey);
        if (new Set(points).size !== points.length) collisions.push(`${example.metadata.title}::${id}`);
      }
      expect(model.diagnostics, example.metadata.title).toHaveLength(0);
    }
    expect(collisions, collisions.join(", ")).toHaveLength(0);
  });

  it("coerces non-finite coordinates so no anchor is NaN", () => {
    const model = buildSchematicModel(
      circuit(
        [
          { id: "R1", type: "resistor", value: "", part: "", x: NaN as unknown as number, y: 0, pins: { "1": "1", "2": "2" } },
          { id: "R2", type: "resistor", value: "", part: "", x: 10, y: 0, pins: { "1": "1", "2": "2" } },
        ],
        [{ name: "N", pins: ["R1.1", "R2.1"] }]
      )
    );
    for (const comp of model.components) {
      for (const anchor of Object.values(comp.anchors)) {
        expect(Number.isFinite(anchor.x) && Number.isFinite(anchor.y)).toBe(true);
      }
    }
  });

  it("spreads components that share one coordinate instead of stacking them", () => {
    const comps = ["R1", "R2", "R3"].map((id) => ({
      id, type: "resistor" as const, value: "", part: "", x: 5, y: 5, pins: { "1": "1", "2": "2" },
    }));
    const model = buildSchematicModel(circuit(comps));
    const points = new Set(model.components.map((c) => ptKey(c.point)));
    expect(points.size).toBe(comps.length);
  });
});
