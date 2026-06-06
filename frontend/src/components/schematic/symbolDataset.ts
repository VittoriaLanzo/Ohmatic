import type { KnownComponentType } from "../../types/circuit";

export type SymbolSvgPair = {
  ansi: string;
  iec: string;
};

export const SCHEMATIC_SYMBOL_DATASET_PROVENANCE = {
  source: "self-authored-inline-svg-dataset",
  license: "CC0-1.0",
  externalAssets: false,
} as const;

const zResistor = `<path d="M-26 0 L-18 0 L-14 -8 L-6 8 L2 -8 L10 8 L18 -8 L22 0 L26 0"/>`;
const boxResistor = `<path d="M-28 0 H-18 M18 0 H28"/><rect x="-18" y="-8" width="36" height="16" rx="1"/>`;
const diodeAnsi = `<path d="M-26 0 H-12 M12 0 H26 M-12 -12 L10 0 L-12 12 Z M12 -13 V13"/>`;
const diodeIec = `<rect x="-22" y="-15" width="44" height="30" rx="1"/><path d="M-28 0 H-22 M22 0 H28 M-11 -8 L6 0 L-11 8 Z M8 -9 V9"/>`;
const transistorAnsi = `<circle cx="0" cy="0" r="18"/><path d="M-28 0 H-8 M-8 -12 V12 M-8 -10 L18 -18 M-8 10 L18 18"/>`;
const transistorIec = `<path d="M-28 0 H-8 M-8 -14 V14 M-8 -11 L18 -18 M-8 11 L18 18 M20 -18 V18"/>`;

function block(label: string) {
  return `<rect x="-26" y="-18" width="52" height="36" rx="4"/><text y="4" text-anchor="middle">${label}</text>`;
}

function iecBlock(label: string) {
  return `<rect x="-26" y="-18" width="52" height="36" rx="1"/><path d="M-18 -18 V18 M18 -18 V18"/><text y="4" text-anchor="middle">${label}</text>`;
}

export const SCHEMATIC_SYMBOL_SVGS = {
  resistor: {
    ansi: zResistor,
    iec: boxResistor,
  },
  capacitor: {
    ansi: `<path d="M-28 0 H-6 M-6 -14 V14 M6 -14 V14 M6 0 H28"/>`,
    iec: `<path d="M-28 0 H-8 M8 0 H28 M-8 -14 V14 M8 -14 V14 M-12 -14 H-8 M8 -14 H12 M-12 14 H-8 M8 14 H12"/>`,
  },
  inductor: {
    ansi: `<path d="M-28 0 H-20 C-20 -10 -10 -10 -10 0 C-10 -10 0 -10 0 0 C0 -10 10 -10 10 0 C10 -10 20 -10 20 0 H28"/>`,
    iec: `<path d="M-28 0 H-18 M18 0 H28"/><rect x="-18" y="-10" width="36" height="20" rx="1"/><path d="M-10 -5 V5 M0 -5 V5 M10 -5 V5"/>`,
  },
  potentiometer: {
    ansi: `${zResistor}<path d="M2 -18 L-7 -7 M2 -18 L-1 -8 M2 -18 L-8 -15"/>`,
    iec: `${boxResistor}<path d="M2 -20 L-8 -8 M2 -20 L-2 -9 M2 -20 L-9 -16"/>`,
  },
  thermistor: {
    ansi: `${zResistor}<path d="M-12 15 L12 -15 M12 -15 H20"/>`,
    iec: `${boxResistor}<path d="M-11 13 L11 -13 M11 -13 H19"/>`,
  },
  varistor: {
    ansi: `${zResistor}<path d="M-12 13 L12 -13"/>`,
    iec: `${boxResistor}<path d="M-11 12 L11 -12"/>`,
  },
  diode: {
    ansi: diodeAnsi,
    iec: `${diodeIec}<text y="24" text-anchor="middle">D</text>`,
  },
  led: {
    ansi: `${diodeAnsi}<path d="M12 -16 L22 -26 M18 -13 L28 -23"/>`,
    iec: `${diodeIec}<path d="M10 -12 L18 -20 M15 -10 L23 -18"/><text y="24" text-anchor="middle">LED</text>`,
  },
  led_rgb: {
    ansi: `${diodeAnsi}<path d="M12 -16 L22 -26 M18 -13 L28 -23 M2 16 V23"/><text y="31" text-anchor="middle">RGB</text>`,
    iec: `${diodeIec}<path d="M10 -12 L18 -20 M15 -10 L23 -18 M-6 12 V18 M0 12 V20 M6 12 V18"/><text y="24" text-anchor="middle">RGB</text>`,
  },
  zener_diode: {
    ansi: `${diodeAnsi}<path d="M12 -13 L18 -18 M12 13 L6 18"/>`,
    iec: `${diodeIec}<path d="M8 -9 L13 -13 M8 9 L3 13"/><text y="24" text-anchor="middle">ZD</text>`,
  },
  schottky_diode: {
    ansi: `${diodeAnsi}<path d="M12 -13 H18 M12 13 H6"/>`,
    iec: `${diodeIec}<path d="M8 -9 H13 M8 9 H3"/><text y="24" text-anchor="middle">SD</text>`,
  },
  tvs_diode: {
    ansi: `${diodeAnsi}<path d="M12 -13 L18 -18 M12 13 L6 18 M-12 -13 L-18 -18 M-12 13 L-6 18"/>`,
    iec: `${diodeIec}<path d="M8 -9 L13 -13 M8 9 L3 13 M-15 -9 L-20 -13 M-15 9 L-10 13"/><text y="24" text-anchor="middle">TVS</text>`,
  },
  photodiode: {
    ansi: `${diodeAnsi}<path d="M28 -26 L18 -16 M31 -20 L21 -10"/>`,
    iec: `${diodeIec}<path d="M20 -20 L12 -12 M25 -16 L17 -8"/><text y="24" text-anchor="middle">PD</text>`,
  },
  diode_bridge: {
    ansi: `<path d="M0 -24 L24 0 L0 24 L-24 0 Z M-28 0 H-17 M17 0 H28 M0 -28 V-17 M0 17 V28 M-12 -6 L0 -14 L12 -6 M0 14 L12 6 L-12 6"/>`,
    iec: `<rect x="-22" y="-18" width="44" height="36" rx="1"/><path d="M-28 0 H-22 M22 0 H28 M0 -28 V-18 M0 18 V28"/><text y="4" text-anchor="middle">BR</text>`,
  },
  transistor_npn: {
    ansi: `${transistorAnsi}<path d="M0 6 L8 12"/>`,
    iec: `${transistorIec}<path d="M0 6 L8 12"/>`,
  },
  transistor_pnp: {
    ansi: `${transistorAnsi}<path d="M8 12 L0 6"/>`,
    iec: `${transistorIec}<path d="M8 12 L0 6"/>`,
  },
  mosfet_n: {
    ansi: `<circle cx="0" cy="0" r="18"/><path d="M-28 0 H-10 M-10 -14 V14 M-4 -12 V12 M4 -12 V12 M4 -10 L18 -18 M4 10 L18 18 M0 6 L8 12"/>`,
    iec: `${transistorIec}<path d="M-3 -14 V14 M4 -10 V10 M0 6 L8 12"/>`,
  },
  mosfet_p: {
    ansi: `<circle cx="0" cy="0" r="18"/><path d="M-28 0 H-10 M-10 -14 V14 M-4 -12 V12 M4 -12 V12 M4 -10 L18 -18 M4 10 L18 18 M8 12 L0 6"/>`,
    iec: `${transistorIec}<path d="M-3 -14 V14 M4 -10 V10 M8 12 L0 6"/>`,
  },
  igbt: {
    ansi: `${transistorAnsi}<path d="M0 6 L8 12"/><text x="5" y="4" text-anchor="middle">IG</text>`,
    iec: `${transistorIec}<path d="M0 6 L8 12"/><text x="5" y="4" text-anchor="middle">IG</text>`,
  },
  phototransistor: {
    ansi: `${transistorAnsi}<path d="M0 6 L8 12 M-26 -20 L-17 -11 M-24 -11 L-15 -2"/>`,
    iec: `${transistorIec}<path d="M0 6 L8 12 M-26 -20 L-17 -11 M-24 -11 L-15 -2"/>`,
  },
  thyristor_scr: {
    ansi: `${diodeAnsi}<path d="M0 15 V25"/>`,
    iec: `<rect x="-20" y="-15" width="40" height="30" rx="1"/><path d="M-28 0 H-20 M20 0 H28 M0 15 V26"/><text y="4" text-anchor="middle">SCR</text>`,
  },
  triac: {
    ansi: `${diodeAnsi}<path d="M0 15 V25 M12 -12 L-10 0 L12 12 Z"/>`,
    iec: `<rect x="-20" y="-15" width="40" height="30" rx="1"/><path d="M-28 0 H-20 M20 0 H28 M0 15 V26"/><text y="4" text-anchor="middle">TRIAC</text>`,
  },
  optocoupler: {
    ansi: `<rect x="-25" y="-18" width="50" height="36" rx="3"/><path d="M-30 -10 H-16 M-16 -17 L-2 -10 L-16 -3 Z M-2 -17 V-3 M4 0 H16 M16 -12 V12 M16 -10 L28 -17 M16 10 L28 17 M-2 -2 L7 -8 M-1 5 L8 -1"/>`,
    iec: `<rect x="-25" y="-18" width="50" height="36" rx="1"/><path d="M0 -18 V18 M-30 -8 H-25 M25 -8 H30 M25 8 H30"/><text x="-13" y="4" text-anchor="middle">LED</text><text x="13" y="4" text-anchor="middle">Q</text>`,
  },
  fuse: {
    ansi: `<path d="M-28 0 H-18 C-8 -13 8 13 18 0 H28"/>`,
    iec: `<path d="M-28 0 H-18 M18 0 H28"/><rect x="-18" y="-7" width="36" height="14" rx="1"/><path d="M-12 0 H12"/>`,
  },
  relay: {
    ansi: `<rect x="-25" y="-18" width="50" height="36" rx="3"/><path d="M-30 -10 H-18 C-18 -17 -8 -17 -8 -10 C-8 -17 2 -17 2 -10 H8 M4 8 H14 M14 8 L28 -5 M22 8 H30"/>`,
    iec: `<rect x="-25" y="-18" width="50" height="36" rx="1"/><path d="M-30 -9 H-25 M-30 9 H-25 M25 -9 H30 M25 9 H30"/><text y="4" text-anchor="middle">K</text>`,
  },
  relay_solid_state: {
    ansi: `<rect x="-25" y="-18" width="50" height="36" rx="3"/><path d="M-30 -8 H-17 M-17 -14 L-5 -8 L-17 -2 Z M-4 -14 V-2 M6 -10 H28 M6 10 H28 M8 -10 L22 10"/>`,
    iec: `<rect x="-25" y="-18" width="50" height="36" rx="1"/><path d="M-30 -9 H-25 M-30 9 H-25 M25 -9 H30 M25 9 H30"/><text y="4" text-anchor="middle">SSR</text>`,
  },
  transformer: {
    ansi: `<path d="M-30 -10 H-22 C-22 -18 -13 -18 -13 -10 C-13 -18 -4 -18 -4 -10 M-30 10 H-22 C-22 2 -13 2 -13 10 C-13 2 -4 2 -4 10 M30 -10 H22 C22 -18 13 -18 13 -10 C13 -18 4 -18 4 -10 M30 10 H22 C22 2 13 2 13 10 C13 2 4 2 4 10 M-1 -18 V18 M2 -18 V18"/>`,
    iec: `<rect x="-24" y="-16" width="18" height="32" rx="1"/><rect x="6" y="-16" width="18" height="32" rx="1"/><path d="M-30 -10 H-24 M-30 10 H-24 M24 -10 H30 M24 10 H30 M-2 -18 V18 M2 -18 V18"/>`,
  },
  ferrite_bead: {
    ansi: `<path d="M-28 0 H-20 C-20 -10 -10 -10 -10 0 C-10 -10 0 -10 0 0 C0 -10 10 -10 10 0 C10 -10 20 -10 20 0 H28"/><rect x="-13" y="-13" width="26" height="26" rx="2"/>`,
    iec: `<path d="M-28 0 H-18 M18 0 H28"/><rect x="-18" y="-10" width="36" height="20" rx="1"/><path d="M-10 -5 V5 M0 -5 V5 M10 -5 V5"/>`,
  },
  seven_segment: {
    ansi: `<rect x="-26" y="-18" width="52" height="36" rx="3"/><path d="M-10 -10 H10 M-12 -8 V0 M12 -8 V0 M-10 0 H10 M-12 2 V10 M12 2 V10 M-10 12 H10"/>`,
    iec: `${iecBlock("7SEG")}`,
  },
  lcd: {
    ansi: `<rect x="-26" y="-18" width="52" height="36" rx="3"/><rect x="-18" y="-10" width="36" height="20" rx="2"/><path d="M-13 -4 H13 M-13 4 H6"/>`,
    iec: `${iecBlock("LCD")}`,
  },
  ic_timer: {
    ansi: block("555"),
    iec: iecBlock("555"),
  },
  ic_opamp: {
    ansi: `<path d="M-24 -18 V18 L26 0 Z"/><text x="-12" y="-6" text-anchor="middle">-</text><text x="-12" y="11" text-anchor="middle">+</text>`,
    iec: iecBlock("OP"),
  },
  ic_comparator: {
    ansi: `<path d="M-24 -18 V18 L26 0 Z"/><text x="-12" y="-6" text-anchor="middle">-</text><text x="-12" y="11" text-anchor="middle">+</text><path d="M16 -6 H25"/>`,
    iec: iecBlock("COMP"),
  },
  ic_regulator: {
    ansi: block("REG"),
    iec: iecBlock("REG"),
  },
  ic_instrumentation_amp: {
    ansi: `<path d="M-24 -18 V18 L26 0 Z"/><text x="-12" y="-6" text-anchor="middle">-</text><text x="-12" y="11" text-anchor="middle">+</text><text x="4" y="4" text-anchor="middle">IA</text>`,
    iec: iecBlock("IA"),
  },
  ic_voltage_ref: {
    ansi: block("REF"),
    iec: iecBlock("REF"),
  },
  ic_adc: {
    ansi: block("ADC"),
    iec: iecBlock("ADC"),
  },
  ic_dac: {
    ansi: block("DAC"),
    iec: iecBlock("DAC"),
  },
  ic_pll: {
    ansi: block("PLL"),
    iec: iecBlock("PLL"),
  },
  ic_logic: {
    ansi: `<path d="M-24 -18 H-2 C18 -18 24 0 -2 18 H-24 Z M-30 -8 H-24 M-30 8 H-24 M24 0 H30"/>`,
    iec: `<rect x="-24" y="-18" width="48" height="36" rx="1"/><path d="M-30 -8 H-24 M-30 8 H-24 M24 0 H30"/><text y="4" text-anchor="middle">&amp;</text>`,
  },
  ic_mcu: {
    ansi: block("MCU"),
    iec: iecBlock("MCU"),
  },
  ic_driver: {
    ansi: block("DRV"),
    iec: iecBlock("DRV"),
  },
  ic_memory: {
    ansi: block("MEM"),
    iec: iecBlock("MEM"),
  },
  ic_fpga: {
    ansi: block("FPGA"),
    iec: iecBlock("FPGA"),
  },
  ic_level_shifter: {
    ansi: block("LVL"),
    iec: iecBlock("LVL"),
  },
  ic_interface: {
    ansi: block("I/O"),
    iec: iecBlock("I/O"),
  },
  ic_filter: {
    ansi: block("FLT"),
    iec: iecBlock("FLT"),
  },
  ic_audio_amp: {
    ansi: `<path d="M-24 -18 V18 L26 0 Z"/><text x="-12" y="-6" text-anchor="middle">-</text><text x="-12" y="11" text-anchor="middle">+</text><text x="4" y="4" text-anchor="middle">AF</text>`,
    iec: iecBlock("AF"),
  },
  ic_battery_management: {
    ansi: block("BMS"),
    iec: iecBlock("BMS"),
  },
  ic_battery_charger: {
    ansi: block("CHG"),
    iec: iecBlock("CHG"),
  },
  ic_protection: {
    ansi: block("PROT"),
    iec: iecBlock("PROT"),
  },
  ic_power_converter: {
    ansi: block("PWR"),
    iec: iecBlock("PWR"),
  },
  ic_rtc: {
    ansi: block("RTC"),
    iec: iecBlock("RTC"),
  },
  ic_rf: {
    ansi: block("RF"),
    iec: iecBlock("RF"),
  },
  power_vcc: {
    ansi: `<path d="M0 23 V5 M-12 5 H12"/><text y="-2" text-anchor="middle">VCC</text>`,
    iec: `<path d="M0 23 V11 M-13 11 H13 V-5 H-13 Z"/><text y="-10" text-anchor="middle">VCC</text>`,
  },
  power_gnd: {
    ansi: `<path d="M0 -23 V-8 M-14 -8 H14 M-9 -3 H9 M-4 2 H4"/>`,
    iec: `<path d="M0 -23 V-7 M-12 -7 L0 10 L12 -7 Z"/>`,
  },
  power_vee: {
    ansi: `<path d="M0 -23 V-6 M-12 -6 H12"/><text y="9" text-anchor="middle">VEE</text>`,
    iec: `<path d="M0 -23 V-11 M-12 -11 H12 V4 H-12 Z"/><text y="18" text-anchor="middle">VEE</text>`,
  },
  power_3v3: {
    ansi: `<path d="M0 23 V5 M-12 5 H12"/><text y="-2" text-anchor="middle">3V3</text>`,
    iec: `<path d="M0 23 V11 M-13 11 H13 V-5 H-13 Z"/><text y="-10" text-anchor="middle">3V3</text>`,
  },
  power_5v: {
    ansi: `<path d="M0 23 V5 M-12 5 H12"/><text y="-2" text-anchor="middle">5V</text>`,
    iec: `<path d="M0 23 V11 M-13 11 H13 V-5 H-13 Z"/><text y="-10" text-anchor="middle">5V</text>`,
  },
  power_12v: {
    ansi: `<path d="M0 23 V5 M-12 5 H12"/><text y="-2" text-anchor="middle">12V</text>`,
    iec: `<path d="M0 23 V11 M-13 11 H13 V-5 H-13 Z"/><text y="-10" text-anchor="middle">12V</text>`,
  },
  battery: {
    ansi: `<path d="M0 -28 V-10 M-12 -10 H12 M-7 0 H7 M-12 10 H12 M0 10 V28"/>`,
    iec: `<path d="M0 -28 V-16 M-16 -16 H16 V16 H-16 Z M0 16 V28 M-7 -9 H7 M-3 9 H3"/>`,
  },
  connector: {
    ansi: `<rect x="-22" y="-16" width="44" height="32" rx="3"/><path d="M-28 -8 H-22 M-28 0 H-22 M-28 8 H-22 M22 -8 H28 M22 0 H28 M22 8 H28"/>`,
    iec: `<rect x="-24" y="-16" width="48" height="32" rx="1"/><path d="M-12 -16 V16 M0 -16 V16 M12 -16 V16"/><text y="4" text-anchor="middle">X</text>`,
  },
  button: {
    ansi: `<path d="M-28 0 H-8 M10 0 H28 M-8 0 L10 -13 M0 -20 V-13 M-9 -20 H9"/>`,
    iec: `<path d="M-28 0 H-10 M10 0 H28 M-10 0 H10"/><rect x="-12" y="-14" width="24" height="28" rx="2"/><path d="M0 -22 V-14 M-10 -22 H10"/>`,
  },
  switch: {
    ansi: `<path d="M-28 0 H-8 M10 0 H28 M-8 0 L10 -13"/>`,
    iec: `<path d="M-28 0 H-10 M10 0 H28 M-10 0 H10"/><rect x="-12" y="-14" width="24" height="28" rx="2"/>`,
  },
  motor_dc: {
    ansi: `<circle cx="0" cy="0" r="18"/><path d="M-28 0 H-18 M18 0 H28"/><text y="4" text-anchor="middle">M</text>`,
    iec: `<rect x="-22" y="-16" width="44" height="32" rx="1"/><path d="M-28 0 H-22 M22 0 H28"/><text y="4" text-anchor="middle">M</text>`,
  },
  motor_stepper: {
    ansi: `<circle cx="0" cy="0" r="18"/><path d="M-28 0 H-18 M18 0 H28"/><text y="4" text-anchor="middle">ST</text>`,
    iec: `<rect x="-22" y="-16" width="44" height="32" rx="1"/><path d="M-28 0 H-22 M22 0 H28"/><text y="4" text-anchor="middle">STEP</text>`,
  },
  servo: {
    ansi: `<circle cx="0" cy="0" r="18"/><path d="M-28 0 H-18 M18 0 H28 M18 0 H27 M27 -6 V6"/><text y="4" text-anchor="middle">SV</text>`,
    iec: `<rect x="-22" y="-16" width="44" height="32" rx="1"/><path d="M-28 0 H-22 M22 0 H28 M22 -6 H28 M22 6 H28"/><text y="4" text-anchor="middle">SERVO</text>`,
  },
  antenna: {
    ansi: `<path d="M0 23 V-8 M0 -8 L-18 -22 M0 -8 L18 -22 M-10 2 C-21 -8 -21 -17 -10 -27 M10 2 C21 -8 21 -17 10 -27"/>`,
    iec: `<path d="M0 23 V-10 M-16 -10 H16 M-11 -16 H11 M-6 -22 H6"/>`,
  },
  crystal: {
    ansi: `<path d="M-28 0 H-14 M14 0 H28 M-14 -14 V14 M14 -14 V14 M-8 -10 H8 V10 H-8 Z"/>`,
    iec: `<rect x="-16" y="-13" width="32" height="26" rx="1"/><path d="M-28 0 H-16 M16 0 H28 M-20 -11 V11 M20 -11 V11"/>`,
  },
  speaker: {
    ansi: `<path d="M-28 -8 H-14 L0 -18 V18 L-14 8 H-28 Z M8 -10 C16 -4 16 4 8 10"/>`,
    iec: `<rect x="-24" y="-16" width="48" height="32" rx="1"/><path d="M-30 0 H-24 M24 0 H30"/><text y="4" text-anchor="middle">SPK</text>`,
  },
  sensor: {
    ansi: `<path d="M-22 -14 H14 V14 H-22 Z M14 -9 L26 -16 M14 0 L26 0 M14 9 L26 16"/>`,
    iec: `<rect x="-24" y="-16" width="48" height="32" rx="1"/><path d="M-30 0 H-24 M24 0 H30"/><text y="4" text-anchor="middle">SENS</text>`,
  },
  microphone: {
    ansi: `<path d="M-24 0 H-10 M-10 -14 H8 V14 H-10 Z M12 -10 C20 -4 20 4 12 10"/>`,
    iec: `<rect x="-24" y="-16" width="48" height="32" rx="1"/><path d="M-30 0 H-24 M24 0 H30"/><text y="4" text-anchor="middle">MIC</text>`,
  },
} satisfies Record<KnownComponentType, SymbolSvgPair>;
