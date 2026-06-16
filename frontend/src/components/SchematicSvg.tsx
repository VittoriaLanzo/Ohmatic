import type { CSSProperties } from "react";
import type { OhmaticCircuitV01 } from "../types/circuit";
import { buildSchematicModel } from "./schematic/model";
import { renderSchematicSymbol, type SymbolStyle } from "./schematic/symbols";

type SchematicSvgProps = {
  circuit: OhmaticCircuitV01 | null;
  phase: "idle" | "submitting" | "polling" | "done" | "error";
  symbolStyle?: SymbolStyle;
  zoom?: number;
};

export function SchematicSvg({ circuit, phase, symbolStyle = "ansi", zoom = 1 }: SchematicSvgProps) {
  if (!circuit) {
    return (
      <div className={`empty-schematic is-${phase}`} role="status">
        <span className="empty-schematic__trace" aria-hidden="true" />
        <span className="empty-schematic__packet" aria-hidden="true" />
        <p>Schematic will appear here.</p>
      </div>
    );
  }

  const model = buildSchematicModel(circuit);
  const desc = [circuit.metadata.description, model.accessibleDiagnostics].filter(Boolean).join("; ");
  // Canvas is sized to the grid the model laid out, so the schematic scales to the
  // circuit instead of cramming every component into a fixed 360x210 box.
  const w = model.width;
  const h = model.height;
  const cx = w / 2;
  const cy = h / 2;

  return (
    <svg
      className={`schematic-svg is-${phase}`}
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label={circuit.metadata.title}
      aria-describedby="schematic-desc schematic-diagnostics"
      style={{ "--schematic-zoom": zoom } as CSSProperties}
    >
      <desc id="schematic-desc">{desc}</desc>
      <defs>
        <pattern id="grid" width="18" height="18" patternUnits="userSpaceOnUse">
          <path d="M 18 0 L 0 0 0 18" fill="none" stroke="rgba(26, 26, 20, 0.08)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width={w} height={h} rx="6" fill="#f9f8f1" />
      <rect x="10" y="10" width={w - 20} height={h - 20} rx="4" fill="url(#grid)" />

      <g className="schematic-viewport" transform={`translate(${cx} ${cy}) scale(${zoom}) translate(${-cx} ${-cy})`}>
        <g className="schematic-nets">
          {model.routes.map((route, index) => (
            <g key={route.name} data-route-kind={route.kind}>
              <title>{`Net ${route.name}: ${route.anchorRefs.join(", ")}`}</title>
              {route.segments.map((segment, segmentIndex) => (
                <path
                  key={`${route.name}-${segmentIndex}`}
                  d={segment}
                  className={`net-line net-line-${index % 5}`}
                  pathLength="1"
                  style={{ "--draw-order": index } as CSSProperties}
                />
              ))}
              <text
                x={route.label.x}
                y={route.label.y}
                className="net-label"
                style={{ "--draw-order": index } as CSSProperties}
              >
                {route.name}
              </text>
            </g>
          ))}
        </g>

        <g className="schematic-components">
          {model.components.map((component, index) => (
            <g
              key={component.id}
              transform={`translate(${component.point.x} ${component.point.y})`}
              className="schematic-component"
              data-component-type={component.type}
              style={{ "--draw-order": index } as CSSProperties}
            >
              <title>{componentTitle(component)}</title>
              {/* Opaque backing: any net routed behind a component is masked by its
                  body, so a passing wire never reads as a false connection through it. */}
              <rect className="component-backing" x="-27" y="-21" width="54" height="42" rx="4" fill="#f9f8f1" />
              {renderSchematicSymbol(component.type, symbolStyle)}
              {Object.entries(component.anchors).map(([pinName, anchor]) => (
                <g key={`${component.id}.${pinName}`} data-pin-anchor={`${component.id}.${pinName}`}>
                  <circle cx={anchor.x - component.point.x} cy={anchor.y - component.point.y} r="1.35" />
                  <text
                    x={anchor.x - component.point.x}
                    y={anchor.y - component.point.y - 4}
                    textAnchor="middle"
                    className="pin-label"
                  >
                    {pinName}
                  </text>
                </g>
              ))}
              <text y="30" textAnchor="middle" className="component-id">
                {component.id}
              </text>
              <text y="40" textAnchor="middle" className="component-type">
                {component.value || component.part || component.type}
              </text>
            </g>
          ))}
        </g>

        <g className="schematic-diagnostics">
          {model.diagnostics.map((diagnostic, index) => (
            <g
              key={`${diagnostic.net}-${diagnostic.ref}-${index}`}
              className="schematic-diagnostic-marker"
              transform={`translate(${diagnostic.point.x + 18} ${diagnostic.point.y - 18})`}
              role="note"
              aria-label={diagnostic.message}
            >
              <circle r="7" />
              <text y="3" textAnchor="middle">
                !
              </text>
            </g>
          ))}
        </g>
      </g>

      {model.diagnostics.length > 0 && (
        <g className="schematic-diagnostic-summary">
          <rect x="14" y={h - 34} width="150" height="20" rx="4" />
          <text x="22" y={h - 20}>
            Pin ref issue
          </text>
        </g>
      )}
      <text id="schematic-diagnostics" className="sr-only-svg">
        {model.accessibleDiagnostics}
      </text>
    </svg>
  );
}

function componentTitle(component: { id: string; type: string; value: string; part: string }) {
  return [component.id, component.type, component.value || component.part].filter(Boolean).join(" - ");
}
