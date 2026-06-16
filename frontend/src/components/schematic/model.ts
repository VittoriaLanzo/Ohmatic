import type { CircuitComponent, OhmaticCircuitV01 } from "../../types/circuit";
import { getSymbolEntry, type AnchorSpec } from "./symbols";

export type Point = {
  x: number;
  y: number;
};

export type SchematicDiagnostic = {
  kind: "malformed_ref" | "unknown_component" | "unknown_pin" | "duplicate_ref";
  ref: string;
  net: string;
  visible: true;
  point: Point;
  message: string;
};

export type SchematicComponentModel = {
  id: string;
  type: string;
  value: string;
  part: string;
  point: Point;
  anchors: Record<string, Point>;
};

export type SchematicRoute = {
  name: string;
  kind: "wire" | "bus";
  anchorRefs: string[];
  segments: string[];
  label: Point;
};

export type SchematicModel = {
  components: SchematicComponentModel[];
  routes: SchematicRoute[];
  diagnostics: SchematicDiagnostic[];
  accessibleDiagnostics: string;
  // Canvas grows with the circuit so components are never squeezed into one band.
  width: number;
  height: number;
};

const ANCHOR_POINTS: Record<AnchorSpec, Point> = {
  left: { x: -31, y: 0 },
  right: { x: 31, y: 0 },
  top: { x: 0, y: -23 },
  bottom: { x: 0, y: 23 },
  "left-top": { x: -31, y: -10 },
  "left-bottom": { x: -31, y: 10 },
  "right-top": { x: 31, y: -10 },
  "right-bottom": { x: 31, y: 10 },
};

// Grid + inter-cell routing lattice. Components sit at cell centres; the boundary
// lines between cells are guaranteed clear of every component body, so a wire that
// only ever rides those lines cannot cross a component. (Orthogonal channel routing
// in the spirit of Adaptagrams/dagre/maxGraph -- our own implementation.)
const CELL_W = 140;
const CELL_H = 120;
const MARGIN = 48;
const TRACKS = 6;
const TRACK_GAP = 4;

type Placement = { point: Point; col: number; row: number };
type Layout = { byId: Map<string, Placement>; cols: number; rows: number; width: number; height: number };

export function buildSchematicModel(circuit: OhmaticCircuitV01): SchematicModel {
  const layout = computeLayout(circuit);
  const componentById = new Map(circuit.components.map((component) => [component.id, component]));
  const components = circuit.components.map((component) =>
    buildComponentModel(component, layout.byId.get(component.id)?.point ?? { x: 0, y: 0 })
  );
  const modelById = new Map(components.map((component) => [component.id, component]));
  const diagnostics: SchematicDiagnostic[] = [];
  const routes: SchematicRoute[] = [];
  let trackIndex = 0;

  for (const net of circuit.nets) {
    const seenRefs = new Set<string>();
    const pins: Array<{ ref: string; point: Point; place: Placement }> = [];

    for (const ref of net.pins) {
      if (seenRefs.has(ref)) {
        diagnostics.push(makeDiagnostic("duplicate_ref", ref, net.name, modelById, `duplicate pin ref ${ref}`));
        continue;
      }
      seenRefs.add(ref);

      const parsed = parsePinRef(ref);
      if (!parsed) {
        diagnostics.push(makeDiagnostic("malformed_ref", ref, net.name, modelById, `malformed pin ref ${ref}`));
        continue;
      }

      const component = componentById.get(parsed.componentId);
      const componentModel = modelById.get(parsed.componentId);
      const place = layout.byId.get(parsed.componentId);
      if (!component || !componentModel || !place) {
        diagnostics.push(makeDiagnostic("unknown_component", ref, net.name, modelById, `unknown component ${ref}`));
        continue;
      }
      if (!Object.prototype.hasOwnProperty.call(component.pins, parsed.pinName)) {
        diagnostics.push(makeDiagnostic("unknown_pin", ref, net.name, modelById, `unknown pin ${ref}`));
        continue;
      }

      pins.push({
        ref,
        point:
          componentModel.anchors[parsed.pinName] ??
          distributePinAnchor(componentModel.point, Object.keys(component.pins), parsed.pinName),
        place,
      });
    }

    if (pins.length >= 2) {
      routes.push(routeNet(net.name, pins, layout.rows, trackIndex));
      trackIndex += 1;
    }
  }

  return {
    components,
    routes,
    diagnostics,
    accessibleDiagnostics: diagnostics.map((diagnostic) => diagnostic.message).join("; "),
    width: layout.width,
    height: layout.height,
  };
}

function computeLayout(circuit: OhmaticCircuitV01): Layout {
  const comps = circuit.components;
  const n = comps.length;
  if (n === 0) {
    return { byId: new Map(), cols: 0, rows: 0, width: 360, height: 210 };
  }
  // Slightly-wide grid reads better than a tall one for schematics.
  const cols = Math.max(1, Math.round(Math.sqrt(n * 1.7)));
  const rows = Math.ceil(n / cols);

  // Finite-guard the model coordinates (a partial layout stage can emit NaN/null),
  // then order top-to-bottom, left-to-right so the grid loosely preserves intent.
  const items = comps.map((component, index) => ({
    id: component.id,
    index,
    x: Number.isFinite(component.x) ? component.x : 0,
    y: Number.isFinite(component.y) ? component.y : 0,
  }));
  items.sort((a, b) => a.y - b.y || a.x - b.x || a.index - b.index);

  const byId = new Map<string, Placement>();
  for (let row = 0; row < rows; row += 1) {
    const rowItems = items
      .slice(row * cols, (row + 1) * cols)
      .sort((a, b) => a.x - b.x || a.index - b.index);
    rowItems.forEach((item, col) => {
      byId.set(item.id, {
        point: { x: MARGIN + col * CELL_W + CELL_W / 2, y: MARGIN + row * CELL_H + CELL_H / 2 },
        col,
        row,
      });
    });
  }

  return { byId, cols, rows, width: MARGIN * 2 + cols * CELL_W, height: MARGIN * 2 + rows * CELL_H };
}

function buildComponentModel(component: CircuitComponent, point: Point): SchematicComponentModel {
  const entry = getSymbolEntry(component.type);
  const pinNames = Object.keys(component.pins);
  const anchors: Record<string, Point> = {};

  // Track occupied anchor offsets so a distributed (unmapped) pin can never land on
  // a mapped pin's anchor: two pins at one point would overlap two different nets.
  const occupied = new Set<string>();
  const slot = (p: Point) => `${Math.round(p.x - point.x)},${Math.round(p.y - point.y)}`;

  const unmapped: string[] = [];
  pinNames.forEach((pinName) => {
    const spec = entry.anchors[pinName] ?? entry.anchors[pinName.toUpperCase()] ?? entry.anchors[pinName.toLowerCase()];
    if (spec) {
      const anchor = offset(point, ANCHOR_POINTS[spec]);
      anchors[pinName] = anchor;
      occupied.add(slot(anchor));
    } else {
      unmapped.push(pinName);
    }
  });

  unmapped.forEach((pinName) => {
    let anchor = distributePinAnchor(point, pinNames, pinName);
    // Nudge down a row at a time until the slot is free (keeps the column, avoids
    // overlap). Bounded so a pathological pin count can never spin.
    for (let guard = 0; occupied.has(slot(anchor)) && guard < 16; guard += 1) {
      anchor = { x: anchor.x, y: anchor.y + 12 };
    }
    anchors[pinName] = anchor;
    occupied.add(slot(anchor));
  });

  return {
    id: component.id,
    type: component.type,
    value: component.value,
    part: component.part,
    point,
    anchors,
  };
}

// ---- routing -------------------------------------------------------------

function latticeY(j: number): number {
  return MARGIN + j * CELL_H;
}

// Each pin turns onto a vertical riser just outside its own body (RISER_OFFSET from
// the component centre), not at the far cell edge -- so the visible pin lead is
// short instead of overflowing across the cell. The riser sits in the gap between
// columns, which is clear of every body top-to-bottom, so it can run to any trunk
// row without crossing a component. The trunk rides a row-boundary gap, clear
// across every column. `off` shifts this net onto its own track to avoid overdraw.
// Must stay clear of the outermost pin anchor (31) even after the largest negative
// track offset, so the lead always points outward; and inside the cell half (70).
const RISER_OFFSET = 46;

function routeNet(
  name: string,
  pins: Array<{ ref: string; point: Point; place: Placement }>,
  rows: number,
  trackIndex: number
): SchematicRoute {
  const off = (trackIndex % TRACKS) * TRACK_GAP - ((TRACKS - 1) * TRACK_GAP) / 2;
  const centroidX = pins.reduce((sum, pin) => sum + pin.place.point.x, 0) / pins.length;

  // Trunk on the row-boundary nearest the pins; each riser runs to it.
  const avgY = pins.reduce((sum, pin) => sum + pin.point.y, 0) / pins.length;
  const jt = clamp(Math.round((avgY - MARGIN) / CELL_H), 0, rows);
  const yt = latticeY(jt) + off;

  // Where each pin turns onto its vertical riser:
  //  - a side pin (left/right anchor) turns just outside its own body;
  //  - a top/bottom pin drops STRAIGHT down its own centre when the trunk is on the
  //    side it points (no sideways jog), else falls back to a side riser.
  const risers = pins.map((pin) => {
    const dx = pin.point.x - pin.place.point.x;
    const dy = pin.point.y - pin.place.point.y;
    if (Math.abs(dx) >= 12) {
      return { x: pin.place.point.x + Math.sign(dx) * RISER_OFFSET + off, y: pin.point.y, anchor: pin.point };
    }
    // Straight drop only to the pin's own adjacent cell boundary stays inside the
    // cell and is therefore clear; a farther trunk would cross same-column bodies,
    // so route it out to a side riser in the clear inter-column gap instead. A
    // straight drop aligns exactly to the pin (no track offset) so the wire leaves
    // the symbol dead-centre rather than jogging a few px sideways.
    const adjacentBoundary = dy < 0 ? pin.place.row : pin.place.row + 1;
    const side = centroidX >= pin.place.point.x ? 1 : -1;
    const x = jt === adjacentBoundary ? pin.point.x : pin.place.point.x + side * RISER_OFFSET + off;
    return { x, y: pin.point.y, anchor: pin.point };
  });

  const segments: string[] = risers
    .filter((riser) => Math.abs(riser.anchor.x - riser.x) > 0.5)
    .map((riser) => `M ${r(riser.anchor.x)} ${r(riser.anchor.y)} H ${r(riser.x)}`);

  const xs = risers.map((riser) => riser.x);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  if (maxX > minX) {
    segments.push(`M ${r(minX)} ${r(yt)} H ${r(maxX)}`);
  }
  for (const riser of risers) {
    if (Math.abs(riser.y - yt) > 0.5) {
      segments.push(`M ${r(riser.x)} ${r(riser.y)} V ${r(yt)}`);
    }
  }

  return {
    name,
    kind: pins.length > 2 ? "bus" : "wire",
    anchorRefs: pins.map((pin) => pin.ref),
    segments,
    label: { x: r(minX + 4), y: r(yt - 6) },
  };
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

function r(value: number): number {
  return Math.round(value * 100) / 100;
}

function parsePinRef(ref: string): { componentId: string; pinName: string } | null {
  const match = /^([A-Z][A-Za-z0-9_]*)\.([A-Za-z0-9_+\-]+)$/.exec(ref);
  if (!match) {
    return null;
  }
  return { componentId: match[1], pinName: match[2] };
}

function makeDiagnostic(
  kind: SchematicDiagnostic["kind"],
  ref: string,
  net: string,
  modelById: Map<string, SchematicComponentModel>,
  message: string
): SchematicDiagnostic {
  const componentId = ref.includes(".") ? ref.split(".")[0] : "";
  const point = modelById.get(componentId)?.point ?? { x: 24, y: 24 };
  return { kind, ref, net, visible: true, point, message };
}

function distributePinAnchor(point: Point, pinNames: string[], pinName: string): Point {
  const index = Math.max(pinNames.indexOf(pinName), 0);
  const side = index % 2 === 0 ? "left" : "right";
  const rank = Math.floor(index / 2);
  const y = (rank - Math.max(Math.ceil(pinNames.length / 2) - 1, 0) / 2) * 12;
  return offset(point, { x: side === "left" ? -31 : 31, y });
}

function offset(point: Point, delta: Point): Point {
  return { x: point.x + delta.x, y: point.y + delta.y };
}
