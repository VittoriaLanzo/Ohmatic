// Hand-authored circuit data model — derived from shared/schema/circuit_v01.json
// but NOT machine-generated. ComponentType is a transparent string newtype
// (not an enum) so that new types can be added via component_registry.toml alone.
//
// DO NOT run typify-cli codegen against this file — it would overwrite the
// ComponentType newtype with an enum and break the data-driven registry design.
// To add a new component type: see verifier/config/component_registry.toml.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OhmaticCircuitV01 {
    pub metadata: CircuitMetadata,
    pub components: Vec<Component>,
    pub nets: Vec<Net>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CircuitMetadata {
    pub title: String,
    pub description: String,
    pub version: String,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Component {
    pub id: String,
    #[serde(rename = "type")]
    pub component_type: ComponentType,
    pub value: String,
    pub part: String,
    pub x: f64,
    pub y: f64,
    pub pins: std::collections::HashMap<String, String>,
}

/// A component type identifier — any lowercase snake_case string.
///
/// Ohmatic is data-driven: the authoritative list of supported types lives in
/// `verifier/config/component_registry.toml`.  To register a new component:
///   1. Add an entry to `component_registry.toml` (bbox, ref_prefix, description).
///   2. Optionally add a named constant to `ohmatic_types::component_types` for
///      use in the rules engine — no other Rust change is required.
///
/// Unknown types (strings not present in the registry) pass serde but are
/// rejected by the verifier as a T1-PARSE error.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(transparent)]
pub struct ComponentType(pub String);

impl ComponentType {
    /// Construct from any string (no validity check — registry is the authority).
    pub fn new(s: impl Into<String>) -> Self {
        Self(s.into())
    }

    /// Borrow the inner string slice.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Display for ComponentType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl From<&str> for ComponentType {
    fn from(s: &str) -> Self {
        Self(s.to_string())
    }
}

impl From<String> for ComponentType {
    fn from(s: String) -> Self {
        Self(s)
    }
}

/// Named string constants for all well-known component types.
///
/// Import with `use ohmatic_types::component_types as ct;` then use `ct::LED`,
/// `ct::RESISTOR`, etc. in pattern matching and array slices.
///
/// Adding a new type does NOT require adding a constant here — it only requires
/// a registry entry.  Constants are provided as a convenience for the rules
/// engine and are informational only.
pub mod component_types {
    // ── Passives ─────────────────────────────────────────────────────────────
    pub const RESISTOR: &str = "resistor";
    pub const CAPACITOR: &str = "capacitor";
    pub const INDUCTOR: &str = "inductor";
    pub const POTENTIOMETER: &str = "potentiometer";
    pub const THERMISTOR: &str = "thermistor";
    pub const VARISTOR: &str = "varistor";

    // ── Diodes ───────────────────────────────────────────────────────────────
    pub const DIODE: &str = "diode";
    pub const LED: &str = "led";
    pub const LED_RGB: &str = "led_rgb";
    pub const ZENER_DIODE: &str = "zener_diode";
    pub const SCHOTTKY_DIODE: &str = "schottky_diode";
    pub const TVS_DIODE: &str = "tvs_diode";
    pub const PHOTODIODE: &str = "photodiode";

    // ── Bipolar transistors ───────────────────────────────────────────────────
    pub const TRANSISTOR_NPN: &str = "transistor_npn";
    pub const TRANSISTOR_PNP: &str = "transistor_pnp";

    // ── Field-effect & power transistors ─────────────────────────────────────
    pub const MOSFET_N: &str = "mosfet_n";
    pub const MOSFET_P: &str = "mosfet_p";
    pub const IGBT: &str = "igbt";
    pub const PHOTOTRANSISTOR: &str = "phototransistor";

    // ── Thyristors & AC power devices ────────────────────────────────────────
    pub const THYRISTOR_SCR: &str = "thyristor_scr";
    pub const TRIAC: &str = "triac";

    // ── Optoelectronics ───────────────────────────────────────────────────────
    pub const OPTOCOUPLER: &str = "optocoupler";

    // ── Protection & switching ────────────────────────────────────────────────
    pub const FUSE: &str = "fuse";
    pub const RELAY: &str = "relay";
    pub const RELAY_SOLID_STATE: &str = "relay_solid_state";

    // ── Magnetics ─────────────────────────────────────────────────────────────
    pub const TRANSFORMER: &str = "transformer";
    pub const FERRITE_BEAD: &str = "ferrite_bead";

    // ── Displays ──────────────────────────────────────────────────────────────
    pub const SEVEN_SEGMENT: &str = "seven_segment";
    pub const LCD: &str = "lcd";

    // ── ICs — analog ──────────────────────────────────────────────────────────
    pub const IC_TIMER: &str = "ic_timer";
    pub const IC_OPAMP: &str = "ic_opamp";
    pub const IC_COMPARATOR: &str = "ic_comparator";
    pub const IC_REGULATOR: &str = "ic_regulator";
    pub const IC_INSTRUMENTATION_AMP: &str = "ic_instrumentation_amp";
    pub const IC_VOLTAGE_REF: &str = "ic_voltage_ref";
    pub const IC_ADC: &str = "ic_adc";
    pub const IC_DAC: &str = "ic_dac";
    pub const IC_PLL: &str = "ic_pll";

    // ── ICs — digital / mixed-signal ──────────────────────────────────────────
    pub const IC_LOGIC: &str = "ic_logic";
    pub const IC_MCU: &str = "ic_mcu";
    pub const IC_DRIVER: &str = "ic_driver";
    pub const IC_MEMORY: &str = "ic_memory";
    pub const IC_FPGA: &str = "ic_fpga";
    pub const IC_LEVEL_SHIFTER: &str = "ic_level_shifter";
    pub const IC_INTERFACE: &str = "ic_interface";
    pub const IC_FILTER: &str = "ic_filter";
    pub const IC_AUDIO_AMP: &str = "ic_audio_amp";
    pub const IC_BATTERY_MANAGEMENT: &str = "ic_battery_management";
    pub const IC_POWER_CONVERTER: &str = "ic_power_converter";
    pub const IC_RTC: &str = "ic_rtc";
    pub const IC_RF: &str = "ic_rf";

    // ── Power symbols ─────────────────────────────────────────────────────────
    pub const POWER_VCC: &str = "power_vcc";
    pub const POWER_GND: &str = "power_gnd";
    pub const POWER_VEE: &str = "power_vee";
    pub const POWER_3V3: &str = "power_3v3";
    pub const POWER_5V: &str = "power_5v";
    pub const POWER_12V: &str = "power_12v";

    // ── Power sources ─────────────────────────────────────────────────────────
    pub const BATTERY: &str = "battery";

    // ── Electromechanical / interface ─────────────────────────────────────────
    pub const CONNECTOR: &str = "connector";
    pub const BUTTON: &str = "button";
    pub const SWITCH: &str = "switch";
    pub const MOTOR_DC: &str = "motor_dc";
    pub const MOTOR_STEPPER: &str = "motor_stepper";
    pub const SERVO: &str = "servo";

    // ── RF / wireless ─────────────────────────────────────────────────────────
    pub const ANTENNA: &str = "antenna";

    // ── Sensors / transducers / output devices ────────────────────────────────
    pub const CRYSTAL: &str = "crystal";
    pub const SPEAKER: &str = "speaker";
    pub const SENSOR: &str = "sensor";
    pub const MICROPHONE: &str = "microphone";
    pub const DIODE_BRIDGE: &str = "diode_bridge";
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Net {
    pub name: String,
    pub pins: Vec<String>,
}

fn is_valid_component_id(id: &str) -> bool {
    let mut chars = id.chars();
    match chars.next() {
        Some(c) if c.is_ascii_uppercase() => chars.all(|c| c.is_ascii_alphanumeric() || c == '_'),
        _ => false,
    }
}

fn is_valid_pin_ref(pin_ref: &str) -> bool {
    match pin_ref.split_once('.') {
        Some((comp_id, pin_name)) => {
            !pin_name.is_empty()
                && is_valid_component_id(comp_id)
                && pin_name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
        }
        None => false,
    }
}

impl OhmaticCircuitV01 {
    pub fn validate(&self) -> Result<(), Vec<String>> {
        use std::collections::{HashMap, HashSet};
        let mut errors: Vec<String> = Vec::new();

        // --- metadata ---
        if self.metadata.version != "0.1" {
            errors.push(format!(
                "version must be \"0.1\", got \"{}\"",
                self.metadata.version
            ));
        }
        if self.metadata.title.is_empty() {
            errors.push("metadata.title must not be empty".to_string());
        }
        if self.metadata.description.is_empty() {
            errors.push("metadata.description must not be empty".to_string());
        }
        if self.metadata.tags.is_empty() {
            errors.push("metadata.tags must have at least one item".to_string());
        } else {
            let mut seen_tags: HashSet<&str> = HashSet::new();
            for tag in &self.metadata.tags {
                if tag.is_empty() {
                    errors.push("metadata.tags items must be non-empty strings".to_string());
                } else if !seen_tags.insert(tag.as_str()) {
                    errors.push(format!(
                        "metadata.tags must not contain duplicate values: '{}'",
                        tag
                    ));
                }
            }
        }

        // --- components — two-pass: count IDs so comp_pins excludes all duplicate-ID
        // components (mirrors validate.py's comp_id_counts approach). Power-type flags
        // are only set from the first (non-duplicate) occurrence of each ID.
        let mut comp_pins: HashMap<&str, HashSet<&str>> = HashMap::new();
        if self.components.is_empty() {
            errors.push("components must not be empty".to_string());
        } else {
            let mut id_counts: HashMap<&str, usize> = HashMap::new();
            for comp in &self.components {
                *id_counts.entry(comp.id.as_str()).or_insert(0) += 1;
            }
            let mut seen_ids: HashSet<&str> = HashSet::new();
            let mut has_vcc = false;
            let mut has_gnd = false;
            for comp in &self.components {
                if comp.id.len() > 64 {
                    errors.push(format!(
                        "component '{}...' id too long (max 64 chars)",
                        &comp.id[..32.min(comp.id.len())]
                    ));
                } else if !is_valid_component_id(&comp.id) {
                    errors.push(format!(
                        "component '{}' id violates pattern ^[A-Z][A-Za-z0-9_]*$",
                        comp.id
                    ));
                }
                let is_dup = !seen_ids.insert(comp.id.as_str());
                if is_dup {
                    errors.push(format!("Duplicate component id: {}", comp.id));
                } else {
                    if comp.component_type.as_str() == component_types::POWER_VCC {
                        has_vcc = true;
                    }
                    if comp.component_type.as_str() == component_types::POWER_GND {
                        has_gnd = true;
                    }
                    if comp.pins.is_empty() {
                        errors.push(format!("component '{}' pins must not be empty", comp.id));
                    } else {
                        for (pin_name, net_label) in &comp.pins {
                            if net_label.is_empty() {
                                errors.push(format!(
                                    "component '{}' pin '{}' has an empty net label",
                                    comp.id, pin_name
                                ));
                            }
                        }
                    }
                    // Always populate comp_pins with the first occurrence's pins.
                    // Duplicates are already flagged by T1-04; suppressing comp_pins for them
                    // causes spurious T1-07 "unknown component" errors for every net that
                    // references the duplicated component.
                    if !comp_pins.contains_key(comp.id.as_str()) {
                        comp_pins.insert(
                            comp.id.as_str(),
                            comp.pins.keys().map(String::as_str).collect(),
                        );
                    }
                }
            }
            if !has_vcc {
                errors.push("Missing required power_vcc component".to_string());
            }
            if !has_gnd {
                errors.push("Missing required power_gnd component".to_string());
            }
        }

        // --- nets ---
        if self.nets.is_empty() {
            errors.push("nets must not be empty".to_string());
        } else {
            let mut seen_net_names: HashSet<&str> = HashSet::new();
            let mut all_pin_refs: HashSet<&str> = HashSet::new();
            let mut used_pins: HashSet<&str> = HashSet::new();
            // One short error per pin regardless of how many nets contain it
            let mut reported_shorts: HashSet<&str> = HashSet::new();
            for net in &self.nets {
                if net.name.is_empty() {
                    errors.push("net name must not be empty".to_string());
                    continue;
                }
                if !seen_net_names.insert(net.name.as_str()) {
                    errors.push(format!("Duplicate net name: {}", net.name));
                    continue;
                }
                if net.pins.len() < 2 {
                    errors.push(format!(
                        "net '{}' must have at least 2 pins, got {}",
                        net.name,
                        net.pins.len()
                    ));
                    // Don't skip — still validate pin refs to populate used_pins and
                    // avoid false "not connected" errors for pins only in this net.
                }
                let mut seen_in_net: HashSet<&str> = HashSet::new();
                for pin in &net.pins {
                    if !is_valid_pin_ref(pin) {
                        errors.push(format!("net '{}' invalid pin ref: {}", net.name, pin));
                        continue;
                    }
                    if !seen_in_net.insert(pin.as_str()) {
                        errors.push(format!(
                            "net '{}' contains duplicate pin ref: {}",
                            net.name, pin
                        ));
                        continue;
                    }
                    let (comp_id, pin_name) = pin.split_once('.').unwrap(); // guaranteed by is_valid_pin_ref
                    match comp_pins.get(comp_id) {
                        None => {
                            errors.push(format!(
                                "net '{}' references unknown component: {}",
                                net.name, comp_id
                            ));
                        }
                        Some(pins) if !pins.contains(pin_name) => {
                            errors.push(format!(
                                "net '{}' references unknown pin {} on {}",
                                net.name, pin_name, comp_id
                            ));
                        }
                        Some(_) => {
                            if !all_pin_refs.insert(pin.as_str()) {
                                if reported_shorts.insert(pin.as_str()) {
                                    errors.push(format!(
                                        "pin ref {} appears in more than one net (electrical short)",
                                        pin
                                    ));
                                }
                            }
                            used_pins.insert(pin.as_str());
                        }
                    }
                }
            }
            // all component pins must be connected to at least one net
            for (comp_id, pins) in &comp_pins {
                for pin_name in pins {
                    let pin_ref = format!("{}.{}", comp_id, pin_name);
                    if !used_pins.contains(pin_ref.as_str()) {
                        errors.push(format!(
                            "component pin {}.{} not connected to any net",
                            comp_id, pin_name
                        ));
                    }
                }
            }
        }

        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }
}
