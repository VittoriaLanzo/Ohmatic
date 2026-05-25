export type KnownComponentType =
  | "resistor"
  | "capacitor"
  | "inductor"
  | "potentiometer"
  | "thermistor"
  | "varistor"
  | "diode"
  | "led"
  | "led_rgb"
  | "zener_diode"
  | "schottky_diode"
  | "tvs_diode"
  | "photodiode"
  | "diode_bridge"
  | "transistor_npn"
  | "transistor_pnp"
  | "mosfet_n"
  | "mosfet_p"
  | "igbt"
  | "phototransistor"
  | "thyristor_scr"
  | "triac"
  | "optocoupler"
  | "fuse"
  | "relay"
  | "relay_solid_state"
  | "transformer"
  | "ferrite_bead"
  | "seven_segment"
  | "lcd"
  | "ic_timer"
  | "ic_opamp"
  | "ic_comparator"
  | "ic_regulator"
  | "ic_instrumentation_amp"
  | "ic_voltage_ref"
  | "ic_adc"
  | "ic_dac"
  | "ic_pll"
  | "ic_logic"
  | "ic_mcu"
  | "ic_driver"
  | "ic_memory"
  | "ic_fpga"
  | "ic_level_shifter"
  | "ic_interface"
  | "ic_filter"
  | "ic_audio_amp"
  | "ic_battery_management"
  | "ic_power_converter"
  | "ic_rtc"
  | "ic_rf"
  | "power_vcc"
  | "power_gnd"
  | "power_vee"
  | "power_3v3"
  | "power_5v"
  | "power_12v"
  | "battery"
  | "connector"
  | "button"
  | "switch"
  | "motor_dc"
  | "motor_stepper"
  | "servo"
  | "antenna"
  | "crystal"
  | "speaker"
  | "sensor"
  | "microphone";

export type ComponentType = KnownComponentType | (string & {});

export type CircuitMetadata = {
  title: string;
  description: string;
  version: "0.1";
  tags: string[];
  [key: string]: unknown;
};

export type CircuitComponent = {
  id: string;
  type: ComponentType;
  value: string;
  part: string;
  x: number;
  y: number;
  pins: Record<string, string>;
};

export type CircuitNet = {
  name: string;
  pins: string[];
};

export type OhmaticCircuitV01 = {
  metadata: CircuitMetadata;
  components: CircuitComponent[];
  nets: CircuitNet[];
  [key: string]: unknown;
};
