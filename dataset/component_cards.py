#!/usr/bin/env python3
"""Public component reference cards.

One card per Ohmatic component type: pins, role, an example part/value, and a
short placement note. This is product reference data (it mirrors the public
component registry in verifier/config/component_registry.toml) and is imported by
the ERC engine (eval/diagnostics). It is deliberately separate from the private
corpus-generation methodology so the latter can live off the public repo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentCard:
    component_type: str
    pins: tuple[str, ...]
    role: str
    part: str
    value: str
    natural_name: str
    support_note: str


COMPONENT_CARDS: dict[str, ComponentCard] = {
    "resistor": ComponentCard("resistor", ("1", "2"), "sets current or divides voltage", "0603", "10k", "resistor", "place in series or divider paths"),
    "capacitor": ComponentCard("capacitor", ("1", "2"), "stores charge, filters rails, or couples AC", "0603", "100nF", "capacitor", "place across rails or signal return"),
    "inductor": ComponentCard("inductor", ("1", "2"), "stores magnetic energy and filters current", "0805", "10uH", "inductor", "place in a filtered or converter path"),
    "potentiometer": ComponentCard("potentiometer", ("A", "W", "B"), "adjustable divider or trim input", "TH-3", "10k", "potentiometer", "connect ends to rails and wiper to signal"),
    "thermistor": ComponentCard("thermistor", ("1", "2"), "temperature-dependent resistor", "0603", "10k NTC", "thermistor", "use with a divider sense node"),
    "varistor": ComponentCard("varistor", ("1", "2"), "clamps surge voltage", "DISC", "14V MOV", "varistor", "place across protected rail and return"),
    "diode": ComponentCard("diode", ("A", "K"), "rectifies or clamps current", "SOD-123", "1N4148", "diode", "respect anode/cathode orientation"),
    "led": ComponentCard("led", ("A", "K"), "visible indicator", "0603", "red", "LED", "requires current limiting"),
    "led_rgb": ComponentCard("led_rgb", ("R", "G", "B", "COM"), "three-channel indicator", "PLCC-4", "RGB", "RGB LED", "each color needs a current path"),
    "zener_diode": ComponentCard("zener_diode", ("A", "K"), "voltage reference or clamp", "SOD-123", "3.3V", "zener diode", "use reverse-biased with impedance"),
    "schottky_diode": ComponentCard("schottky_diode", ("A", "K"), "low-drop rectifier or OR-ing diode", "SOD-123", "SS14", "Schottky diode", "respect current direction"),
    "tvs_diode": ComponentCard("tvs_diode", ("A", "K"), "transient surge clamp", "SMA", "5V TVS", "TVS diode", "place at connector or protected rail"),
    "photodiode": ComponentCard("photodiode", ("A", "K"), "light-to-current sensor", "SMD", "BPW34", "photodiode", "bias into amplifier or resistor"),
    "diode_bridge": ComponentCard("diode_bridge", ("AC1", "AC2", "+", "-"), "full-wave rectifier bridge", "SMD-4", "1A bridge", "bridge rectifier", "connect AC pins to source and DC pins to load"),
    "transistor_npn": ComponentCard("transistor_npn", ("B", "C", "E"), "low-side BJT switch or amplifier", "SOT-23", "2N3904", "NPN transistor", "base needs a resistor path"),
    "transistor_pnp": ComponentCard("transistor_pnp", ("B", "C", "E"), "high-side BJT switch", "SOT-23", "2N3906", "PNP transistor", "base needs a resistor path"),
    "mosfet_n": ComponentCard("mosfet_n", ("G", "D", "S"), "N-channel FET switch", "SOT-23", "2N7002", "N-channel MOSFET", "gate needs defined drive"),
    "mosfet_p": ComponentCard("mosfet_p", ("G", "D", "S"), "P-channel high-side switch", "SOT-23", "AO3401", "P-channel MOSFET", "gate needs pull path"),
    "igbt": ComponentCard("igbt", ("G", "C", "E"), "high-power controlled switch", "TO-220", "IGBT", "IGBT", "gate drive and load path required"),
    "phototransistor": ComponentCard("phototransistor", ("C", "E"), "light-sensitive transistor", "SMD", "PT", "phototransistor", "use with load resistor"),
    "thyristor_scr": ComponentCard("thyristor_scr", ("A", "K", "G"), "latching controlled rectifier", "TO-92", "SCR", "SCR thyristor", "gate trigger must reference cathode"),
    "triac": ComponentCard("triac", ("MT1", "MT2", "G"), "bidirectional AC switch", "TO-220", "TRIAC", "triac", "gate trigger must reference main terminal"),
    "optocoupler": ComponentCard("optocoupler", ("A", "K", "C", "E"), "galvanic isolation", "DIP-4", "PC817", "optocoupler", "input LED and output transistor sides stay separate"),
    "fuse": ComponentCard("fuse", ("1", "2"), "overcurrent protection", "1206", "500mA", "fuse", "place in series with supply"),
    "relay": ComponentCard("relay", ("A1", "A2", "NO", "NC", "COM"), "isolated electromechanical switch", "THT", "5V relay", "relay", "coil and contact sides are distinct"),
    "relay_solid_state": ComponentCard("relay_solid_state", ("IN+", "IN-", "OUT+", "OUT-"), "solid-state isolated switch", "SIP-4", "SSR", "solid-state relay", "input and load sides are distinct"),
    "transformer": ComponentCard("transformer", ("P1", "P2", "S1", "S2"), "isolated magnetic coupling", "XFMR", "1:1", "transformer", "primary and secondary sides are isolated"),
    "ferrite_bead": ComponentCard("ferrite_bead", ("1", "2"), "EMI series impedance", "0603", "600R", "ferrite bead", "place in series with noisy rail"),
    "seven_segment": ComponentCard("seven_segment", ("A", "B", "C", "D", "E", "F", "G", "DP", "COM"), "numeric display", "DIP-10", "1 digit", "seven-segment display", "segments need current paths"),
    "lcd": ComponentCard("lcd", ("VCC", "GND", "RS", "E", "D4", "D5", "D6", "D7"), "character display module", "HDR", "16x2", "LCD", "needs rails and data/control bus"),
    "ic_timer": ComponentCard("ic_timer", ("VCC", "GND", "TRIG", "OUT", "RESET", "CTRL", "THRESH", "DISCH"), "timer or oscillator IC", "SOIC-8", "555", "timer IC", "needs timing network and rails"),
    "ic_opamp": ComponentCard("ic_opamp", ("IN+", "IN-", "OUT", "V+", "V-"), "analog amplifier", "SOIC-8", "op amp", "op-amp", "needs feedback and rails"),
    "ic_comparator": ComponentCard("ic_comparator", ("IN+", "IN-", "OUT", "VCC", "GND"), "threshold detector", "SOIC-8", "LM393", "comparator", "output often needs pull-up"),
    "ic_regulator": ComponentCard("ic_regulator", ("VIN", "VOUT", "GND", "ADJ"), "linear regulator", "SOT-223", "LDO", "regulator", "needs input and output capacitors"),
    "ic_instrumentation_amp": ComponentCard("ic_instrumentation_amp", ("IN+", "IN-", "OUT", "REF", "VCC", "VEE", "RG"), "precision differential amplifier", "SOIC-8", "INA", "instrumentation amplifier", "needs gain resistor and reference"),
    "ic_voltage_ref": ComponentCard("ic_voltage_ref", ("IN", "OUT", "GND"), "precision reference source", "SOT-23", "2.5V ref", "voltage reference", "decouple input and output"),
    "ic_adc": ComponentCard("ic_adc", ("VIN", "VREF", "VCC", "GND", "SDA", "SCL"), "analog-to-digital converter", "MSOP-10", "12-bit ADC", "ADC", "needs reference and bus"),
    "ic_dac": ComponentCard("ic_dac", ("VOUT", "VREF", "VCC", "GND", "SDA", "SCL"), "digital-to-analog converter", "MSOP-10", "12-bit DAC", "DAC", "needs reference and bus"),
    "ic_pll": ComponentCard("ic_pll", ("VCO_IN", "CLK_IN", "CLK_OUT", "VCC", "GND"), "clock synthesizer", "QFN", "PLL", "PLL", "needs clock input and rails"),
    "ic_logic": ComponentCard("ic_logic", ("A", "B", "Y", "VCC", "GND"), "digital logic function", "SOIC-14", "logic gate", "logic IC", "needs rails and logic signals"),
    "ic_mcu": ComponentCard("ic_mcu", ("VCC", "GND", "GPIO1", "GPIO2", "SDA", "SCL", "RESET"), "microcontroller", "QFN-32", "MCU", "microcontroller", "needs rails and bypass capacitor"),
    "ic_driver": ComponentCard("ic_driver", ("IN1", "IN2", "OUT1", "OUT2", "VCC", "GND"), "load or motor driver", "SOIC-8", "driver", "driver IC", "connect control input and load output"),
    "ic_memory": ComponentCard("ic_memory", ("VCC", "GND", "CS", "SCK", "MOSI", "MISO"), "nonvolatile or volatile memory", "SOIC-8", "EEPROM", "memory IC", "needs bus and chip select"),
    "ic_fpga": ComponentCard("ic_fpga", ("VCC", "GND", "IO1", "IO2", "CLK", "CONFIG"), "programmable logic", "BGA", "FPGA", "FPGA", "needs clock, config, and rails"),
    "ic_level_shifter": ComponentCard("ic_level_shifter", ("VCC_A", "VCC_B", "GND", "A1", "B1", "A2", "B2"), "logic voltage translator", "TSSOP", "level shifter", "level shifter", "needs both voltage domains"),
    "ic_interface": ComponentCard("ic_interface", ("VCC", "GND", "TX", "RX", "A", "B"), "serial or differential interface", "SOIC-8", "RS485", "interface IC", "needs bus and rails"),
    "ic_filter": ComponentCard("ic_filter", ("IN", "OUT", "VCC", "GND", "CLK"), "active or switched-cap filter", "SOIC-8", "filter IC", "filter IC", "needs rails and signal path"),
    "ic_audio_amp": ComponentCard("ic_audio_amp", ("IN+", "IN-", "OUT", "VCC", "GND", "BYPASS"), "audio power amplifier", "SOIC-8", "audio amp", "audio amplifier", "needs speaker/load and bypass"),
    "ic_battery_management": ComponentCard("ic_battery_management", ("VIN", "VBAT", "GND", "SDA", "SCL", "STAT"), "charger or fuel gauge", "QFN", "charger", "battery-management IC", "needs battery and input supply"),
    "ic_battery_charger": ComponentCard("ic_battery_charger", ("VIN", "VBAT", "GND", "ISET", "STAT", "EN"), "li-ion/lipo charger", "QFN", "charger", "battery-charger IC", "needs input supply, battery, and bypass"),
    "ic_protection": ComponentCard("ic_protection", ("VDD", "GND", "VM", "DOUT", "COUT", "SENSE"), "battery/load protection", "SOT-23", "protection", "protection IC", "needs supply rail and bypass"),
    "ic_power_converter": ComponentCard("ic_power_converter", ("VIN", "VOUT", "GND", "FB", "EN", "SW"), "switching converter controller", "QFN", "buck converter", "power-converter IC", "needs inductor, feedback, and caps"),
    "ic_rtc": ComponentCard("ic_rtc", ("VCC", "GND", "SDA", "SCL", "INT", "BAT"), "real-time clock", "SOIC-8", "RTC", "RTC", "needs bus, battery, and crystal or clock"),
    "ic_rf": ComponentCard("ic_rf", ("VCC", "GND", "RF", "SDA", "SCL", "IRQ"), "RF transceiver", "QFN", "RF IC", "RF IC", "needs antenna path and rails"),
    "power_vcc": ComponentCard("power_vcc", ("1",), "positive rail symbol", "VCC", "VCC", "VCC rail", "net label only"),
    "power_gnd": ComponentCard("power_gnd", ("1",), "ground rail symbol", "GND", "0V", "ground rail", "net label only"),
    "power_vee": ComponentCard("power_vee", ("1",), "negative rail symbol", "VEE", "-5V", "negative rail", "net label only"),
    "power_3v3": ComponentCard("power_3v3", ("1",), "3.3V rail symbol", "3V3", "3.3V", "3.3V rail", "net label only"),
    "power_5v": ComponentCard("power_5v", ("1",), "5V rail symbol", "5V", "5V", "5V rail", "net label only"),
    "power_12v": ComponentCard("power_12v", ("1",), "12V rail symbol", "12V", "12V", "12V rail", "net label only"),
    "battery": ComponentCard("battery", ("+", "-"), "portable energy source", "BAT", "Li-ion", "battery", "connect polarity correctly"),
    "connector": ComponentCard("connector", ("VCC", "GND", "S1", "S2"), "external interface", "HEADER", "", "connector", "maps internal signals to outside world"),
    "button": ComponentCard("button", ("1", "2"), "momentary input", "TACT", "", "button", "needs pull-up or pull-down path"),
    "switch": ComponentCard("switch", ("1", "2", "COM"), "manual switch", "SPDT", "", "switch", "connect common and selected throw"),
    "motor_dc": ComponentCard("motor_dc", ("1", "2"), "DC motor load", "MOTOR", "6V", "DC motor", "drive through transistor or driver"),
    "motor_stepper": ComponentCard("motor_stepper", ("A+", "A-", "B+", "B-"), "two-phase stepper load", "STEPPER", "bipolar", "stepper motor", "drive coils from stepper driver"),
    "servo": ComponentCard("servo", ("VCC", "GND", "SIG"), "PWM-controlled actuator", "SERVO", "RC", "servo", "needs rail and control signal"),
    "antenna": ComponentCard("antenna", ("RF", "GND"), "RF radiator", "ANT", "2.4GHz", "antenna", "connect RF feed and optional ground"),
    "crystal": ComponentCard("crystal", ("1", "2"), "frequency reference", "SMD", "16MHz", "crystal", "connect across clock pins with load caps"),
    "speaker": ComponentCard("speaker", ("1", "2"), "audio output transducer", "SPK", "8 ohm", "speaker", "drive from amplifier output"),
    "sensor": ComponentCard("sensor", ("VCC", "GND", "OUT"), "generic sensing module", "MODULE", "analog sensor", "sensor", "needs rail and output path"),
    "microphone": ComponentCard("microphone", ("OUT", "GND", "VCC"), "audio input transducer", "MEMS", "mic", "microphone", "bias and AC-couple or amplify"),
}
