// Structs bootstrapped by hand from shared/schema/circuit_v01.json.
// Run: make codegen (requires typify-cli --version 0.4.0) to regenerate ONLY the struct/enum
// definitions above the `fn is_valid_component_id` line.
// DO NOT regenerate: is_valid_component_id, is_valid_pin_ref, and impl OhmaticCircuitV01
// are hand-written and must be preserved.

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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ComponentType {
    Resistor,
    Capacitor,
    Led,
    Diode,
    TransistorNpn,
    TransistorPnp,
    MosfetN,
    MosfetP,
    IcTimer,
    IcOpamp,
    IcRegulator,
    IcLogic,
    IcMcu,
    IcDriver,
    PowerVcc,
    PowerGnd,
    Connector,
    Crystal,
    Inductor,
    Button,
    Speaker,
    Sensor,
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
            let mut dup_tag_reported = false;
            for tag in &self.metadata.tags {
                if tag.is_empty() {
                    errors.push("metadata.tags items must be non-empty strings".to_string());
                } else if !seen_tags.insert(tag.as_str()) && !dup_tag_reported {
                    errors.push("metadata.tags must not contain duplicate values".to_string());
                    dup_tag_reported = true;
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
                if !is_valid_component_id(&comp.id) {
                    errors.push(format!(
                        "component '{}' id violates pattern ^[A-Z][A-Za-z0-9_]*$",
                        comp.id
                    ));
                }
                let is_dup = !seen_ids.insert(comp.id.as_str());
                if is_dup {
                    errors.push(format!("Duplicate component id: {}", comp.id));
                } else {
                    if comp.component_type == ComponentType::PowerVcc { has_vcc = true; }
                    if comp.component_type == ComponentType::PowerGnd { has_gnd = true; }
                    if comp.pins.is_empty() {
                        errors.push(format!("component '{}' pins must not be empty", comp.id));
                    } else if id_counts[comp.id.as_str()] == 1 {
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
