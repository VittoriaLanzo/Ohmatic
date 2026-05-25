use ohmatic_types::OhmaticCircuitV01;

/// DRC severity level for rule findings.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DrcLevel {
    Violation,
    Warning,
    Info,
}

/// A single DRC finding, ready to serialise as "[rule_id] message".
#[derive(Debug, Clone)]
pub struct DrcError {
    pub rule_id: String,
    pub message: String,
    pub level: DrcLevel,
}

impl DrcError {
    pub fn new(rule_id: impl Into<String>, message: impl Into<String>, level: DrcLevel) -> Self {
        Self { rule_id: rule_id.into(), message: message.into(), level }
    }
    /// Serialise to the HTTP wire format: "[T1-04] Duplicate component id: R1"
    pub fn to_wire(&self) -> String {
        format!("[{}] {}", self.rule_id, self.message)
    }
}

/// Assign a Tier-1 rule ID based on the error string prefix.
fn assign_t1_rule_id(err: &str) -> &'static str {
    if err.starts_with("version must be") {
        "T1-01"
    } else if err.starts_with("metadata.") {
        "T1-02"
    } else if err.starts_with("components must not be empty") {
        "T1-03"
    } else if err.starts_with("component '") || err.starts_with("Duplicate component id") {
        "T1-04"
    } else if err.starts_with("Missing required") {
        "T1-05"
    } else if err.starts_with("nets must not be empty")
        || err.starts_with("net name")
        || err.starts_with("Duplicate net")
        || (err.starts_with("net '") && err.contains("must have at least 2 pins"))
    {
        "T1-06"
    } else {
        "T1-07"
    }
}

/// Run Tier 1 structural checks. Returns Err with all DRC violations found.
/// Delegates entirely to `circuit.validate()` — does not reimplement any logic.
pub fn run_tier1(circuit: &OhmaticCircuitV01) -> Result<(), Vec<DrcError>> {
    match circuit.validate() {
        Ok(()) => Ok(()),
        Err(errs) => {
            let drc_errors = errs
                .into_iter()
                .map(|e| {
                    let rule_id = assign_t1_rule_id(&e);
                    DrcError::new(rule_id, e, DrcLevel::Violation)
                })
                .collect();
            Err(drc_errors)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ohmatic_types::{CircuitMetadata, Component, ComponentType, Net, OhmaticCircuitV01};
    use std::collections::HashMap;

    fn valid_circuit() -> OhmaticCircuitV01 {
        OhmaticCircuitV01 {
            metadata: CircuitMetadata {
                title: "Test".to_string(),
                description: "Test circuit".to_string(),
                version: "0.1".to_string(),
                tags: vec!["test".to_string()],
            },
            components: vec![
                Component {
                    id: "VCC1".to_string(),
                    component_type: ComponentType::new("power_vcc"),
                    value: "5V".to_string(),
                    part: "VCC".to_string(),
                    x: 0.0,
                    y: 0.0,
                    pins: HashMap::from([("1".to_string(), "vcc".to_string())]),
                },
                Component {
                    id: "GND1".to_string(),
                    component_type: ComponentType::new("power_gnd"),
                    value: "".to_string(),
                    part: "GND".to_string(),
                    x: 10.0,
                    y: 0.0,
                    pins: HashMap::from([("1".to_string(), "gnd".to_string())]),
                },
                Component {
                    id: "R1".to_string(),
                    component_type: ComponentType::new("resistor"),
                    value: "10k".to_string(),
                    part: "RES".to_string(),
                    x: 5.0,
                    y: 0.0,
                    pins: HashMap::from([
                        ("1".to_string(), "vcc".to_string()),
                        ("2".to_string(), "gnd".to_string()),
                    ]),
                },
            ],
            nets: vec![
                Net {
                    name: "VCC".to_string(),
                    pins: vec!["VCC1.1".to_string(), "R1.1".to_string()],
                },
                Net {
                    name: "GND".to_string(),
                    pins: vec!["GND1.1".to_string(), "R1.2".to_string()],
                },
            ],
        }
    }

    // T1-01: version check

    #[test]
    fn t1_01_pass() {
        let circuit = valid_circuit();
        assert!(run_tier1(&circuit).is_ok());
    }

    #[test]
    fn t1_01_violation() {
        let mut circuit = valid_circuit();
        circuit.metadata.version = "0.99".to_string();
        let result = run_tier1(&circuit);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        let target = errs.iter().find(|e| e.rule_id == "T1-01");
        assert!(target.is_some(), "expected T1-01 error, got: {:?}", errs);
        assert!(
            target.unwrap().to_wire().starts_with("[T1-01]"),
            "to_wire must start with [T1-01]"
        );
    }

    // T1-02: metadata checks

    #[test]
    fn t1_02_pass() {
        let circuit = valid_circuit();
        assert!(run_tier1(&circuit).is_ok());
    }

    #[test]
    fn t1_02_violation() {
        let mut circuit = valid_circuit();
        circuit.metadata.title = "".to_string();
        let result = run_tier1(&circuit);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        let target = errs.iter().find(|e| e.rule_id == "T1-02");
        assert!(target.is_some(), "expected T1-02 error, got: {:?}", errs);
        assert!(
            target.unwrap().to_wire().starts_with("[T1-02]"),
            "to_wire must start with [T1-02]"
        );
    }

    // T1-03: components non-empty

    #[test]
    fn t1_03_pass() {
        let circuit = valid_circuit();
        assert!(run_tier1(&circuit).is_ok());
    }

    #[test]
    fn t1_03_violation() {
        let mut circuit = valid_circuit();
        circuit.components = vec![];
        // Must NOT panic on empty components vec
        let result = run_tier1(&circuit);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        let target = errs.iter().find(|e| e.rule_id == "T1-03");
        assert!(target.is_some(), "expected T1-03 error, got: {:?}", errs);
        assert!(
            target.unwrap().to_wire().starts_with("[T1-03]"),
            "to_wire must start with [T1-03]"
        );
    }

    // T1-04: component ID validity / uniqueness

    #[test]
    fn t1_04_pass() {
        let circuit = valid_circuit();
        assert!(run_tier1(&circuit).is_ok());
    }

    #[test]
    fn t1_04_violation() {
        let mut circuit = valid_circuit();
        // Add a second component with the same ID "R1"
        circuit.components.push(Component {
            id: "R1".to_string(),
            component_type: ComponentType::new("resistor"),
            value: "1k".to_string(),
            part: "RES".to_string(),
            x: 20.0,
            y: 0.0,
            pins: HashMap::from([("1".to_string(), "a".to_string())]),
        });
        let result = run_tier1(&circuit);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        let target = errs.iter().find(|e| e.rule_id == "T1-04");
        assert!(target.is_some(), "expected T1-04 error, got: {:?}", errs);
        assert!(
            target.unwrap().to_wire().starts_with("[T1-04]"),
            "to_wire must start with [T1-04]"
        );
    }

    // T1-05: power VCC / GND presence

    #[test]
    fn t1_05_pass() {
        let circuit = valid_circuit();
        assert!(run_tier1(&circuit).is_ok());
    }

    #[test]
    fn t1_05_violation() {
        let mut circuit = valid_circuit();
        // Replace the VCC component with another resistor — neither component is power_vcc,
        // triggering "Missing required power_vcc component" (T1-05).
        // Use a unique ID (VCC1 is renamed) and rebuild nets to avoid connectivity errors.
        circuit.components[0] = Component {
            id: "R2".to_string(),
            component_type: ComponentType::new("resistor"),
            value: "1k".to_string(),
            part: "RES".to_string(),
            x: 0.0,
            y: 0.0,
            pins: HashMap::from([("1".to_string(), "a".to_string())]),
        };
        circuit.nets = vec![
            Net {
                name: "VCC".to_string(),
                pins: vec!["R2.1".to_string(), "R1.1".to_string()],
            },
            Net {
                name: "GND".to_string(),
                pins: vec!["GND1.1".to_string(), "R1.2".to_string()],
            },
        ];
        // R2 pin "1" is connected; add a net for R2's single pin group — already done above.
        // But R2 has only one pin "1" so net "VCC" covers it.
        // Note: GND1.1 is in GND; R2.1 in VCC; R1.1 in VCC; R1.2 in GND. No short.
        let result = run_tier1(&circuit);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        let target = errs.iter().find(|e| e.rule_id == "T1-05");
        assert!(target.is_some(), "expected T1-05 error, got: {:?}", errs);
        assert!(
            target.unwrap().to_wire().starts_with("[T1-05]"),
            "to_wire must start with [T1-05]"
        );
    }

    // T1-06: nets structural checks (non-empty, min 2 pins)

    #[test]
    fn t1_06_pass() {
        let circuit = valid_circuit();
        assert!(run_tier1(&circuit).is_ok());
    }

    #[test]
    fn t1_06_violation() {
        let mut circuit = valid_circuit();
        // Replace the VCC net with one that has only 1 pin
        circuit.nets[0] = Net {
            name: "VCC".to_string(),
            pins: vec!["VCC1.1".to_string()],
        };
        let result = run_tier1(&circuit);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        let target = errs.iter().find(|e| e.rule_id == "T1-06");
        assert!(target.is_some(), "expected T1-06 error, got: {:?}", errs);
        assert!(
            target.unwrap().to_wire().starts_with("[T1-06]"),
            "to_wire must start with [T1-06]"
        );
    }

    // T1-07: pin reference validity / connectivity

    #[test]
    fn t1_07_pass() {
        let circuit = valid_circuit();
        assert!(run_tier1(&circuit).is_ok());
    }

    #[test]
    fn t1_07_violation() {
        let mut circuit = valid_circuit();
        // Add a net referencing a component "FAKE" that does not exist
        circuit.nets.push(Net {
            name: "ORPHAN".to_string(),
            pins: vec!["FAKE.1".to_string(), "VCC1.1".to_string()],
        });
        let result = run_tier1(&circuit);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        let target = errs.iter().find(|e| e.rule_id == "T1-07");
        assert!(target.is_some(), "expected T1-07 error, got: {:?}", errs);
        assert!(
            target.unwrap().to_wire().starts_with("[T1-07]"),
            "to_wire must start with [T1-07]"
        );
    }

    // Integration test: wrong version → first error is T1-01 and to_wire format is correct

    #[test]
    fn tier1_wrong_version() {
        let mut circuit = valid_circuit();
        circuit.metadata.version = "2.0".to_string();
        let result = run_tier1(&circuit);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert!(!errs.is_empty(), "expected at least one error");
        let first = &errs[0];
        assert_eq!(first.rule_id, "T1-01", "first error rule_id must be T1-01");
        assert!(
            first.to_wire().starts_with("[T1-01]"),
            "to_wire must start with [T1-01], got: {}",
            first.to_wire()
        );
    }

    // Seed circuits test: all 20 circuits in examples.json must pass Tier 1

    #[test]
    fn examples_json_all_pass_tier1() {
        use serde_json::Value;

        // CARGO_MANIFEST_DIR is verifier/ — dataset/ is one level up at workspace root.
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let examples_path = std::path::Path::new(manifest_dir)
            .join("../dataset/examples.json");

        let raw = std::fs::read_to_string(&examples_path).unwrap_or_else(|e| {
            panic!("Failed to read {}: {}", examples_path.display(), e)
        });

        let values: Vec<Value> = serde_json::from_str(&raw)
            .expect("examples.json must be valid JSON array");

        assert!(!values.is_empty(), "examples.json must not be empty");

        for (i, val) in values.iter().enumerate() {
            let circuit: OhmaticCircuitV01 = serde_json::from_value(val.clone())
                .unwrap_or_else(|e| {
                    panic!("Circuit #{} failed to deserialise: {}", i, e)
                });
            let result = run_tier1(&circuit);
            if let Err(ref errs) = result {
                let wires: Vec<String> = errs.iter().map(|e| e.to_wire()).collect();
                panic!(
                    "Circuit #{} ('{}') failed Tier 1:\n  {}",
                    i,
                    circuit.metadata.title,
                    wires.join("\n  ")
                );
            }
        }
    }
}
