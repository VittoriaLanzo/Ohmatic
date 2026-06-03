import type { ReactNode } from "react";
import { KNOWN_COMPONENT_TYPES, type ComponentType, type KnownComponentType } from "../../types/circuit";

export type SymbolStyle = "ansi" | "iec";
export const UNKNOWN_SYMBOL_TYPE = "unknown";

export type AnchorSpec = "left" | "right" | "top" | "bottom" | "left-top" | "left-bottom" | "right-top" | "right-bottom";

export type SchematicSymbolEntry = {
  ansi: { kind: string };
  iec: { kind: string };
  anchors: Record<string, AnchorSpec>;
  label: string;
};

const twoPin = { "1": "left", "2": "right" } as const;
const threePinControl = { B: "left", C: "right-top", E: "right-bottom", G: "left", D: "right-top", S: "right-bottom" } as const;
const powerPin = { "1": "bottom" } as const;
const icPins = { VCC: "top", GND: "bottom", IN: "left", OUT: "right" } as const;

const anchorOverrides: Partial<Record<KnownComponentType, Record<string, AnchorSpec>>> = {
  potentiometer: { A: "left", W: "top", B: "right", ...twoPin },
  led_rgb: { R: "left-top", G: "left", B: "left-bottom", COM: "right" },
  diode_bridge: { AC1: "left", AC2: "right", "+": "top", "-": "bottom" },
  transistor_npn: { B: "left", C: "right-top", E: "right-bottom" },
  transistor_pnp: { B: "left", C: "right-top", E: "right-bottom" },
  mosfet_n: { G: "left", D: "right-top", S: "right-bottom" },
  mosfet_p: { G: "left", D: "right-top", S: "right-bottom" },
  igbt: { G: "left", C: "right-top", E: "right-bottom" },
  phototransistor: { C: "right-top", E: "right-bottom" },
  thyristor_scr: { A: "left", K: "right", G: "bottom" },
  triac: { MT1: "left", MT2: "right", G: "bottom" },
  optocoupler: { A: "left-top", K: "left-bottom", C: "right-top", E: "right-bottom" },
  relay: { A1: "left-top", A2: "left-bottom", COM: "right", NO: "right-top", NC: "right-bottom" },
  relay_solid_state: { "IN+": "left-top", "IN-": "left-bottom", "OUT+": "right-top", "OUT-": "right-bottom" },
  transformer: { P1: "left-top", P2: "left-bottom", S1: "right-top", S2: "right-bottom" },
  ic_opamp: { "IN+": "left-bottom", "IN-": "left-top", OUT: "right", VCC: "top", VEE: "bottom", GND: "bottom" },
  ic_comparator: { "IN+": "left-bottom", "IN-": "left-top", OUT: "right", VCC: "top", GND: "bottom" },
  ic_regulator: { VIN: "left", VOUT: "right", GND: "bottom", ADJ: "right-bottom" },
  ic_battery_charger: { VIN: "left", VBAT: "right", GND: "bottom", ISET: "left-bottom", STAT: "right-bottom", EN: "left-top" },
  ic_protection: { VDD: "top", GND: "bottom", SENSE: "left", GATE: "right" },
  battery: { "+": "top", "-": "bottom", "1": "top", "2": "bottom" },
  power_gnd: { "1": "top" },
  power_vee: { "1": "top" },
  power_vcc: powerPin,
  power_3v3: powerPin,
  power_5v: powerPin,
  power_12v: powerPin,
  motor_stepper: { "A+": "left-top", "A-": "left-bottom", "B+": "right-top", "B-": "right-bottom" },
  servo: { VCC: "left-top", GND: "left-bottom", SIG: "right" },
  antenna: { RF: "bottom", GND: "left-bottom" },
  microphone: { OUT: "right", GND: "bottom", VCC: "top" },
  sensor: { VCC: "top", GND: "bottom", OUT: "right", SIG: "right" },
};

function defaultAnchors(type: KnownComponentType): Record<string, AnchorSpec> {
  if (type.startsWith("ic_") || type === "connector" || type === "lcd" || type === "seven_segment") {
    return icPins;
  }
  if (type.startsWith("transistor_") || type.startsWith("mosfet_")) {
    return threePinControl;
  }
  if (type.startsWith("power_")) {
    return powerPin;
  }
  if (type.includes("diode") || type === "led") {
    return { A: "left", K: "right" };
  }
  return twoPin;
}

export const SCHEMATIC_SYMBOLS: Record<KnownComponentType, SchematicSymbolEntry> = Object.fromEntries(
  KNOWN_COMPONENT_TYPES.map((type) => [
    type,
    {
      ansi: { kind: type },
      iec: { kind: type },
      anchors: anchorOverrides[type] ?? defaultAnchors(type),
      label: type.replace(/^ic_/, "").replace(/_/g, " ").toUpperCase(),
    },
  ])
) as Record<KnownComponentType, SchematicSymbolEntry>;

export function isKnownComponentType(type: ComponentType): type is KnownComponentType {
  return (KNOWN_COMPONENT_TYPES as readonly string[]).includes(type);
}

export function getSymbolEntry(type: ComponentType): SchematicSymbolEntry {
  if (isKnownComponentType(type)) {
    return SCHEMATIC_SYMBOLS[type];
  }
  return {
    ansi: { kind: UNKNOWN_SYMBOL_TYPE },
    iec: { kind: UNKNOWN_SYMBOL_TYPE },
    anchors: twoPin,
    label: "UNKNOWN",
  };
}

export function renderSchematicSymbol(type: ComponentType, mode: SymbolStyle): ReactNode {
  const entry = getSymbolEntry(type);
  const kind = entry[mode].kind;
  const label = entry.label.length > 12 ? entry.label.slice(0, 12) : entry.label;
  const common = { "data-symbol-kind": kind, "data-symbol-mode": mode };

  if (type === "resistor") {
    return mode === "ansi" ? (
      <g {...common}>
        <path d="M-26 0 L-18 0 L-14 -8 L-6 8 L2 -8 L10 8 L18 -8 L22 0 L26 0" />
      </g>
    ) : (
      <g {...common}>
        <path d="M-28 0 H-18 M18 0 H28" />
        <rect x="-18" y="-8" width="36" height="16" rx="1" />
      </g>
    );
  }

  if (type === "capacitor") {
    return (
      <g {...common}>
        <path d="M-28 0 H-6 M-6 -14 V14 M6 -14 V14 M6 0 H28" />
      </g>
    );
  }

  if (type.includes("diode") || type === "led" || type === "led_rgb") {
    return (
      <g {...common}>
        <path d="M-26 0 H-12 M12 0 H26 M-12 -12 L10 0 L-12 12 Z M12 -13 V13" />
        {(type === "led" || type === "led_rgb" || type === "photodiode") && <path d="M12 -16 L22 -26 M18 -13 L28 -23" />}
        {type !== "diode" && type !== "led" && type !== "led_rgb" && <text y="24" textAnchor="middle">{label}</text>}
      </g>
    );
  }

  if (type.startsWith("transistor_") || type.startsWith("mosfet_") || type === "igbt" || type === "phototransistor") {
    return (
      <g {...common}>
        <circle cx="0" cy="0" r="18" />
        <path d="M-28 0 H-8 M-8 -12 V12 M-8 -10 L18 -18 M-8 10 L18 18" />
        <path d={type.includes("_p") || type === "transistor_pnp" ? "M8 12 L0 6" : "M0 6 L8 12"} />
      </g>
    );
  }

  if (type.startsWith("power_")) {
    if (type === "power_gnd") {
      return (
        <g {...common}>
          <path d="M0 -23 V-8 M-14 -8 H14 M-9 -3 H9 M-4 2 H4" />
        </g>
      );
    }

    if (type === "power_vee") {
      return (
        <g {...common}>
          <path d="M0 -23 V-6 M-12 -6 H12" />
          <text y="9" textAnchor="middle">VEE</text>
        </g>
      );
    }

    return (
      <g {...common}>
        <path d="M0 23 V5 M-12 5 H12" />
        <text y="-2" textAnchor="middle">{label.replace("POWER ", "")}</text>
      </g>
    );
  }

  if (type === "battery") {
    return (
      <g {...common}>
        <path d="M0 -28 V-10 M-12 -10 H12 M-7 0 H7 M-12 10 H12 M0 10 V28" />
      </g>
    );
  }

  return (
    <g {...common}>
      <rect x="-26" y="-18" width="52" height="36" rx={type.startsWith("ic_") ? 2 : 4} />
      <text y="4" textAnchor="middle">{label}</text>
    </g>
  );
}
