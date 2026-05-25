import type { CSSProperties } from "react";
import type { OhmaticCircuitV01 } from "../types/circuit";

type SchematicSvgProps = {
  circuit: OhmaticCircuitV01 | null;
  phase: "idle" | "submitting" | "polling" | "done" | "error";
};

export function SchematicSvg({ circuit, phase }: SchematicSvgProps) {
  // CIRCUIT ARTIFACT ENTRY: renders result.circuit returned by the gateway job.
  // Backend agents linking output should preserve metadata/components/nets, coordinates, and pin refs.
  if (!circuit) {
    return (
      <div className={`empty-schematic is-${phase}`} role="status">
        <span className="empty-schematic__trace" aria-hidden="true" />
        <span className="empty-schematic__packet" aria-hidden="true" />
        <p>Schematic will appear here.</p>
      </div>
    );
  }

  const positions = normalizePositions(circuit);

  return (
    <svg
      className={`schematic-svg is-${phase}`}
      viewBox="0 0 360 210"
      role="img"
      aria-labelledby="schematic-title schematic-desc"
    >
      <title id="schematic-title">{circuit.metadata.title}</title>
      <desc id="schematic-desc">{circuit.metadata.description}</desc>
      <defs>
        <pattern id="grid" width="18" height="18" patternUnits="userSpaceOnUse">
          <path d="M 18 0 L 0 0 0 18" fill="none" stroke="rgba(26, 26, 20, 0.08)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width="360" height="210" rx="6" fill="#f9f8f1" />
      <rect x="10" y="10" width="340" height="190" rx="4" fill="url(#grid)" />

      <g className="schematic-nets">
        {circuit.nets.map((net, index) => {
          const points = net.pins
            .map((pin) => positions.get(pin.split(".")[0]))
            .filter((point): point is Point => Boolean(point));
          if (points.length < 2) {
            return null;
          }
          return (
            <g key={net.name}>
              <polyline
                points={points.map((point) => `${point.x},${point.y}`).join(" ")}
                className={`net-line net-line-${index % 5}`}
                pathLength="1"
                style={{ "--draw-order": index } as CSSProperties}
              />
              <text
                x={points[0].x + 8}
                y={points[0].y - 8}
                className="net-label"
                style={{ "--draw-order": index } as CSSProperties}
              >
                {net.name}
              </text>
            </g>
          );
        })}
      </g>

      <g className="schematic-components">
        {circuit.components.map((component, index) => {
          const point = positions.get(component.id) ?? { x: 0, y: 0 };
          return (
            <g
              key={component.id}
              transform={`translate(${point.x} ${point.y})`}
              className="schematic-component"
              style={{ "--draw-order": index } as CSSProperties}
            >
              <ComponentSymbol type={component.type} />
              <circle cx="-29" cy="0" r="2.8" />
              <circle cx="29" cy="0" r="2.8" />
              <text y="-2" textAnchor="middle" className="component-id">
                {component.id}
              </text>
              <text y="10" textAnchor="middle" className="component-type">
                {component.type}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

function ComponentSymbol({ type }: { type: string }) {
  if (type === "resistor") {
    return (
      <g className="symbol-resistor">
        <path d="M-26 0 L-18 0 L-14 -8 L-6 8 L2 -8 L10 8 L18 -8 L22 0 L26 0" />
        <rect x="-25" y="-15" width="50" height="30" rx="4" />
      </g>
    );
  }

  if (type === "led" || type.includes("diode")) {
    return (
      <g className="symbol-led">
        <path d="M-20 10 L-20 -10 L4 0 Z" />
        <path d="M8 -11 L8 11" />
        <path d="M12 -12 L20 -20 M17 -9 L25 -17" />
        <rect x="-25" y="-15" width="50" height="30" rx="4" />
      </g>
    );
  }

  if (type.startsWith("power_") || type === "battery") {
    return (
      <g className="symbol-power">
        <path d="M0 -14 L0 8 M-11 8 L11 8 M-7 13 L7 13 M-3 18 L3 18" />
        <rect x="-25" y="-15" width="50" height="30" rx="4" />
      </g>
    );
  }

  if (type.startsWith("ic_")) {
    return (
      <g className="symbol-ic">
        <rect x="-25" y="-16" width="50" height="32" rx="2" />
        <path d="M-28 -9 L-34 -9 M-28 0 L-34 0 M-28 9 L-34 9 M28 -9 L34 -9 M28 0 L34 0 M28 9 L34 9" />
      </g>
    );
  }

  return <rect x="-25" y="-14" width="50" height="28" rx="4" />;
}

type Point = {
  x: number;
  y: number;
};

function normalizePositions(circuit: OhmaticCircuitV01): Map<string, Point> {
  const xs = circuit.components.map((component) => component.x);
  const ys = circuit.components.map((component) => component.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);

  return new Map(
    circuit.components.map((component) => [
      component.id,
      {
        x: 42 + ((component.x - minX) / spanX) * 276,
        y: 54 + ((component.y - minY) / spanY) * 102
      }
    ])
  );
}
