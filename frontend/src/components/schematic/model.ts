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

export function buildSchematicModel(circuit: OhmaticCircuitV01): SchematicModel {
  const positions = normalizePositions(circuit);
  const componentById = new Map(circuit.components.map((component) => [component.id, component]));
  const components = circuit.components.map((component) => buildComponentModel(component, positions.get(component.id) ?? { x: 0, y: 0 }));
  const modelById = new Map(components.map((component) => [component.id, component]));
  const diagnostics: SchematicDiagnostic[] = [];
  const routes: SchematicRoute[] = [];

  for (const net of circuit.nets) {
    const seenRefs = new Set<string>();
    const anchors: Array<{ ref: string; point: Point }> = [];

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
      if (!component || !componentModel) {
        diagnostics.push(makeDiagnostic("unknown_component", ref, net.name, modelById, `unknown component ${ref}`));
        continue;
      }
      if (!Object.prototype.hasOwnProperty.call(component.pins, parsed.pinName)) {
        diagnostics.push(makeDiagnostic("unknown_pin", ref, net.name, modelById, `unknown pin ${ref}`));
        continue;
      }

      anchors.push({
        ref,
        point: componentModel.anchors[parsed.pinName] ?? distributePinAnchor(componentModel.point, Object.keys(component.pins), parsed.pinName),
      });
    }

    if (anchors.length >= 2) {
      routes.push(buildRoute(net.name, anchors));
    }
  }

  return {
    components,
    routes,
    diagnostics,
    accessibleDiagnostics: diagnostics.map((diagnostic) => diagnostic.message).join("; "),
  };
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

function buildRoute(name: string, anchors: Array<{ ref: string; point: Point }>): SchematicRoute {
  if (anchors.length === 2) {
    const [a, b] = anchors;
    const midX = (a.point.x + b.point.x) / 2;
    return {
      name,
      kind: "wire",
      anchorRefs: anchors.map((anchor) => anchor.ref),
      segments: [`M ${a.point.x} ${a.point.y} H ${midX} V ${b.point.y} H ${b.point.x}`],
      label: { x: midX + 4, y: Math.min(a.point.y, b.point.y) - 8 },
    };
  }

  const minX = Math.min(...anchors.map((anchor) => anchor.point.x));
  const maxX = Math.max(...anchors.map((anchor) => anchor.point.x));
  const trunkY = Math.round(anchors.reduce((sum, anchor) => sum + anchor.point.y, 0) / anchors.length) - 18;
  return {
    name,
    kind: "bus",
    anchorRefs: anchors.map((anchor) => anchor.ref),
    segments: [
      `M ${minX} ${trunkY} H ${maxX}`,
      ...anchors.map((anchor) => `M ${anchor.point.x} ${anchor.point.y} V ${trunkY}`),
    ],
    label: { x: minX + 4, y: trunkY - 8 },
  };
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

function normalizePositions(circuit: OhmaticCircuitV01): Map<string, Point> {
  // Coerce non-finite coordinates (a half-finished layout stage can emit NaN/null)
  // to 0 so they never leak into "M NaN ..." paths that silently drop a component.
  const coords = circuit.components.map((component) => ({
    id: component.id,
    x: Number.isFinite(component.x) ? component.x : 0,
    y: Number.isFinite(component.y) ? component.y : 0,
  }));
  const xs = coords.map((c) => c.x);
  const ys = coords.map((c) => c.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  // Every component at one coordinate (e.g. all-zero layout) would collapse onto a
  // single point; lay them out in a readable row by index instead of one pile.
  if (coords.length > 1 && maxX === minX && maxY === minY) {
    const span = Math.max(coords.length - 1, 1);
    return new Map(coords.map((c, index) => [c.id, { x: 52 + (index / span) * 256, y: 107 }]));
  }

  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);

  return new Map(
    coords.map((c) => [
      c.id,
      {
        x: 52 + ((c.x - minX) / spanX) * 256,
        y: 64 + ((c.y - minY) / spanY) * 86,
      },
    ])
  );
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
