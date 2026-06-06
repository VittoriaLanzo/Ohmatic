import type { ReactNode } from "react";
import { KNOWN_COMPONENT_TYPES, type ComponentType, type KnownComponentType } from "../../types/circuit";
import { SCHEMATIC_SYMBOL_DATASET_PROVENANCE, SCHEMATIC_SYMBOL_SVGS } from "./symbolDataset";

export type SymbolStyle = "ansi" | "iec";
export const UNKNOWN_SYMBOL_TYPE = "unknown";
export const SCHEMATIC_SYMBOL_PROVENANCE = SCHEMATIC_SYMBOL_DATASET_PROVENANCE;

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
const unknownSvg = {
  ansi: `<rect x="-20" y="-14" width="40" height="28" rx="4"/><text y="4" text-anchor="middle">?</text>`,
  iec: `<rect x="-20" y="-14" width="40" height="28" rx="1"/><path d="M-12 -14 V14 M12 -14 V14"/><text y="4" text-anchor="middle">?</text>`,
} satisfies Record<SymbolStyle, string>;

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
      ansi: { kind: `${type}:ansi` },
      iec: { kind: `${type}:iec` },
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
  const svg = isKnownComponentType(type) ? SCHEMATIC_SYMBOL_SVGS[type][mode] : unknownSvg[mode];

  return <g data-symbol-kind={entry[mode].kind} data-symbol-mode={mode} dangerouslySetInnerHTML={{ __html: svg }} />;
}
