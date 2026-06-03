import { describe, expect, it } from "vitest";
import { KNOWN_COMPONENT_TYPES } from "../../types/circuit";
import { SCHEMATIC_SYMBOLS, UNKNOWN_SYMBOL_TYPE } from "./symbols";

const REGISTRY_TYPES = [
  "resistor",
  "capacitor",
  "inductor",
  "potentiometer",
  "thermistor",
  "varistor",
  "diode",
  "led",
  "led_rgb",
  "zener_diode",
  "schottky_diode",
  "tvs_diode",
  "photodiode",
  "diode_bridge",
  "transistor_npn",
  "transistor_pnp",
  "mosfet_n",
  "mosfet_p",
  "igbt",
  "phototransistor",
  "thyristor_scr",
  "triac",
  "optocoupler",
  "fuse",
  "relay",
  "relay_solid_state",
  "transformer",
  "ferrite_bead",
  "seven_segment",
  "lcd",
  "ic_timer",
  "ic_opamp",
  "ic_comparator",
  "ic_regulator",
  "ic_instrumentation_amp",
  "ic_voltage_ref",
  "ic_adc",
  "ic_dac",
  "ic_pll",
  "ic_logic",
  "ic_mcu",
  "ic_driver",
  "ic_memory",
  "ic_fpga",
  "ic_level_shifter",
  "ic_interface",
  "ic_filter",
  "ic_audio_amp",
  "ic_battery_management",
  "ic_battery_charger",
  "ic_protection",
  "ic_power_converter",
  "ic_rtc",
  "ic_rf",
  "power_vcc",
  "power_gnd",
  "power_vee",
  "power_3v3",
  "power_5v",
  "power_12v",
  "battery",
  "connector",
  "button",
  "switch",
  "motor_dc",
  "motor_stepper",
  "servo",
  "antenna",
  "crystal",
  "speaker",
  "sensor",
  "microphone",
] as const;

describe("schematic registry coverage", () => {
  it("keeps frontend known component types aligned with the read-only registry", () => {
    expect([...KNOWN_COMPONENT_TYPES].sort()).toEqual([...REGISTRY_TYPES].sort());
  });

  it("has explicit ANSI and IEC symbol coverage for every known registry type", () => {
    for (const type of REGISTRY_TYPES) {
      expect(SCHEMATIC_SYMBOLS[type], type).toBeDefined();
      expect(SCHEMATIC_SYMBOLS[type].ansi.kind, `${type} ansi`).not.toBe(UNKNOWN_SYMBOL_TYPE);
      expect(SCHEMATIC_SYMBOLS[type].iec.kind, `${type} iec`).not.toBe(UNKNOWN_SYMBOL_TYPE);
      expect(Object.keys(SCHEMATIC_SYMBOLS[type].anchors).length, `${type} anchors`).toBeGreaterThan(0);
    }
  });
});
