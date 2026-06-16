import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { buildSchematicModel } from "./model";
import type { OhmaticCircuitV01 } from "../../types/circuit";

// The product invariant: a net wire must never run across the body of a component
// it is not connected to (that reads as a false connection). The router keeps every
// segment on the inter-cell lattice, so this should hold for any circuit.

const dataset = JSON.parse(
  readFileSync(resolve(__dirname, "../../../../dataset/examples.json"), "utf8")
) as OhmaticCircuitV01[];

// Component body half-extent used as the keep-out box for the test.
const BODY_X = 22;
const BODY_Y = 16;

type Seg = [number, number, number, number];

function parseSegments(d: string): Seg[] {
  const t = d.trim().split(/\s+/);
  const out: Seg[] = [];
  let x = 0;
  let y = 0;
  let i = 0;
  while (i < t.length) {
    const c = t[i++];
    if (c === "M") {
      x = Number(t[i++]);
      y = Number(t[i++]);
    } else if (c === "H") {
      const nx = Number(t[i++]);
      out.push([x, y, nx, y]);
      x = nx;
    } else if (c === "V") {
      const ny = Number(t[i++]);
      out.push([x, y, x, ny]);
      y = ny;
    }
  }
  return out;
}

function crossesBox(seg: Seg, cx: number, cy: number): boolean {
  const [x1, y1, x2, y2] = seg;
  return (
    Math.max(x1, x2) >= cx - BODY_X &&
    Math.min(x1, x2) <= cx + BODY_X &&
    Math.max(y1, y2) >= cy - BODY_Y &&
    Math.min(y1, y2) <= cy + BODY_Y
  );
}

function crossings(circuit: OhmaticCircuitV01): string[] {
  const model = buildSchematicModel(circuit);
  const points = new Map(model.components.map((component) => [component.id, component.point]));
  const found: string[] = [];
  for (const route of model.routes) {
    const members = new Set(route.anchorRefs.map((ref) => ref.split(".")[0]));
    const segs = route.segments.flatMap(parseSegments);
    for (const [id, p] of points) {
      if (members.has(id)) continue;
      if (segs.some((seg) => crossesBox(seg, p.x, p.y))) found.push(`${route.name}->${id}`);
    }
  }
  return found;
}

describe("routing integrity (no wire over a non-member component)", () => {
  it("holds across every checked-in dataset example", () => {
    const offenders: string[] = [];
    for (const circuit of dataset) {
      const found = crossings(circuit);
      if (found.length) offenders.push(`${circuit.metadata.title}: ${found.join(", ")}`);
    }
    expect(offenders, offenders.join(" | ")).toHaveLength(0);
  });

  it("holds for a dense fully-connected stress circuit", () => {
    const ids = Array.from({ length: 12 }, (_, i) => `U${i + 1}`);
    const circuit: OhmaticCircuitV01 = {
      metadata: { title: "dense mesh", description: "", version: "0.1", tags: [] },
      components: ids.map((id, i) => ({
        id,
        type: "ic_mcu",
        value: "",
        part: "",
        x: (i % 4) * 10,
        y: Math.floor(i / 4) * 10,
        pins: { IN: "1", OUT: "2", VCC: "3", GND: "4" },
      })),
      nets: [
        { name: "VCC", pins: ids.map((id) => `${id}.VCC`) },
        { name: "GND", pins: ids.map((id) => `${id}.GND`) },
        ...ids.slice(0, -1).map((id, i) => ({ name: `S${i}`, pins: [`${id}.OUT`, `${ids[i + 1]}.IN`] })),
      ],
    };
    expect(crossings(circuit)).toHaveLength(0);
  });

  it("sizes the canvas to the circuit instead of a fixed box", () => {
    const small = buildSchematicModel(dataset[0]);
    const big = buildSchematicModel({
      ...dataset[0],
      components: Array.from({ length: 16 }, (_, i) => ({
        id: `R${i}`,
        type: "resistor",
        value: "",
        part: "",
        x: i,
        y: i,
        pins: { "1": "1", "2": "2" },
      })),
    });
    expect(big.width).toBeGreaterThan(small.width);
    expect(big.height).toBeGreaterThan(0);
  });
});
