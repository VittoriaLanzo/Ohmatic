//! Stage 0 baseline tests for OhmaticCircuitV01 schema and types.
//! These tests are written before implementation and lock the pre-fix baseline.
//! All tests should pass after Stage 0 implementation is complete.

use ohmatic_types::{CircuitMetadata, Component, ComponentType, Net, OhmaticCircuitV01};
use std::collections::HashMap;

fn minimal_valid_circuit() -> OhmaticCircuitV01 {
    let mut pins = HashMap::new();
    pins.insert("1".to_string(), "1".to_string());
    pins.insert("2".to_string(), "2".to_string());

    OhmaticCircuitV01 {
        metadata: CircuitMetadata {
            title: "Test Circuit".to_string(),
            description: "Minimal test circuit".to_string(),
            version: "0.1".to_string(),
            tags: vec!["test".to_string()],
        },
        components: vec![
            Component {
                id: "R1".to_string(),
                component_type: ComponentType::Resistor,
                value: "10kΩ".to_string(),
                part: "0603".to_string(),
                x: 50.0,
                y: 50.0,
                pins: pins.clone(),
            },
            Component {
                id: "VCC1".to_string(),
                component_type: ComponentType::PowerVcc,
                value: "5V".to_string(),
                part: "VCC".to_string(),
                x: 10.0,
                y: 10.0,
                pins: {
                    let mut p = HashMap::new();
                    p.insert("1".to_string(), "1".to_string());
                    p
                },
            },
            Component {
                id: "GND1".to_string(),
                component_type: ComponentType::PowerGnd,
                value: "".to_string(),
                part: "GND".to_string(),
                x: 90.0,
                y: 90.0,
                pins: {
                    let mut p = HashMap::new();
                    p.insert("1".to_string(), "1".to_string());
                    p
                },
            },
        ],
        nets: vec![
            Net {
                name: "VCC".to_string(),
                pins: vec!["VCC1.1".to_string(), "R1.1".to_string()],
            },
            Net {
                name: "GND".to_string(),
                pins: vec!["R1.2".to_string(), "GND1.1".to_string()],
            },
        ],
    }
}

#[test]
fn test_round_trip_serialization() {
    let circuit = minimal_valid_circuit();
    let json = serde_json::to_string(&circuit).expect("serialization failed");
    let restored: OhmaticCircuitV01 = serde_json::from_str(&json).expect("deserialization failed");
    assert_eq!(circuit, restored);
}

#[test]
fn test_metadata_version_is_0_1() {
    let circuit = minimal_valid_circuit();
    assert_eq!(circuit.metadata.version, "0.1");
}

#[test]
fn test_components_non_empty() {
    let circuit = minimal_valid_circuit();
    assert!(!circuit.components.is_empty());
}

#[test]
fn test_nets_non_empty() {
    let circuit = minimal_valid_circuit();
    assert!(!circuit.nets.is_empty());
}

#[test]
fn test_net_has_at_least_two_pins() {
    let circuit = minimal_valid_circuit();
    for net in &circuit.nets {
        assert!(net.pins.len() >= 2, "Net '{}' has fewer than 2 pins", net.name);
    }
}

#[test]
fn test_component_type_enum_all_variants_deserializable() {
    let types = [
        "resistor", "capacitor", "led", "diode", "transistor_npn", "transistor_pnp",
        "mosfet_n", "mosfet_p", "ic_timer", "ic_opamp", "ic_regulator", "ic_logic",
        "ic_mcu", "ic_driver", "power_vcc", "power_gnd", "connector", "crystal",
        "inductor", "button", "speaker", "sensor",
    ];
    for t in &types {
        let json = format!("\"{}\"", t);
        let result: Result<ComponentType, _> = serde_json::from_str(&json);
        assert!(result.is_ok(), "ComponentType '{}' failed to deserialize", t);
    }
}

#[test]
fn test_unknown_component_type_rejected() {
    let json = "\"unknown_widget\"";
    let result: Result<ComponentType, _> = serde_json::from_str(json);
    assert!(result.is_err(), "unknown_widget should be rejected by ComponentType enum");
}

#[test]
fn test_underscore_id_in_component() {
    let mut pins = HashMap::new();
    pins.insert("1".to_string(), "1".to_string());
    pins.insert("2".to_string(), "2".to_string());

    // C_bypass is a valid component ID in the seed circuits
    let component = Component {
        id: "C_bypass".to_string(),
        component_type: ComponentType::Capacitor,
        value: "100nF".to_string(),
        part: "0402".to_string(),
        x: 170.0,
        y: 120.0,
        pins,
    };
    let json = serde_json::to_string(&component).expect("serialization failed");
    let restored: Component = serde_json::from_str(&json).expect("deserialization failed");
    assert_eq!(restored.id, "C_bypass");
}

#[test]
fn test_coordinate_out_of_300_range_is_valid() {
    // Decision 3: verifier normalizes any range; schema must not reject x=1000
    let mut pins = HashMap::new();
    pins.insert("1".to_string(), "1".to_string());
    let component = Component {
        id: "R1".to_string(),
        component_type: ComponentType::Resistor,
        value: "1kΩ".to_string(),
        part: "0603".to_string(),
        x: 1000.0,
        y: 1000.0,
        pins,
    };
    let json = serde_json::to_string(&component).expect("serialization failed");
    let _restored: Component =
        serde_json::from_str(&json).expect("should deserialize — no coordinate bounds");
}

// ---------------------------------------------------------------------------
// Regression tests — Stage 0 acceptance criteria (AC1, AC3, AC5, AC6, AC7)
// ---------------------------------------------------------------------------

/// AC1 — `shared/schema/circuit_v01.json` is valid JSON and contains all
/// required JSON Schema draft-07 structural fields.
/// Fails pre-fix: `include_str!` compile error if the file is absent.
#[test]
fn test_schema_json_has_required_structure() {
    let raw = include_str!("../../../shared/schema/circuit_v01.json");
    let v: serde_json::Value =
        serde_json::from_str(raw).expect("circuit_v01.json must be valid JSON");

    assert!(
        v.get("$schema").is_some(),
        "circuit_v01.json missing '$schema' key"
    );
    assert!(
        v.get("$id").is_some(),
        "circuit_v01.json missing '$id' key"
    );
    assert!(
        v.get("title").is_some(),
        "circuit_v01.json missing 'title' key"
    );
    assert!(
        v.get("required").is_some(),
        "circuit_v01.json missing 'required' key"
    );
    assert!(
        v.get("properties").is_some(),
        "circuit_v01.json missing 'properties' key"
    );

    // Sanity-check the draft-07 $schema URI
    let schema_uri = v["$schema"].as_str().unwrap_or("");
    assert!(
        schema_uri.contains("draft-07"),
        "circuit_v01.json '$schema' must reference a draft-07 URI (got: {schema_uri})"
    );
}

/// AC3 — Deserialization must fail when a required field is absent.
/// Sub-case A: top-level `nets` field missing → OhmaticCircuitV01 must return Err.
/// Sub-case B: a component object missing `type` field → Component must return Err.
/// Fails pre-fix: OhmaticCircuitV01 / Component types absent.
#[test]
fn test_schema_rejects_missing_required_field() {
    // Sub-case A: missing `nets`
    let missing_nets = r#"{
        "metadata": {
            "title": "No Nets",
            "description": "missing nets field",
            "version": "0.1",
            "tags": ["test"]
        },
        "components": [
            {
                "id": "R1",
                "type": "resistor",
                "value": "10k",
                "part": "0603",
                "x": 10.0,
                "y": 10.0,
                "pins": {"1": "1", "2": "2"}
            }
        ]
    }"#;
    let result_a: Result<OhmaticCircuitV01, _> = serde_json::from_str(missing_nets);
    assert!(
        result_a.is_err(),
        "deserialization should fail when 'nets' field is absent"
    );

    // Sub-case B: component missing `type`
    let missing_type = r#"{
        "id": "R1",
        "value": "10k",
        "part": "0603",
        "x": 10.0,
        "y": 10.0,
        "pins": {"1": "1", "2": "2"}
    }"#;
    let result_b: Result<Component, _> = serde_json::from_str(missing_type);
    assert!(
        result_b.is_err(),
        "deserialization should fail when component 'type' field is absent"
    );
}

/// AC3 — A full circuit whose component has an unrecognised type string must
/// fail to deserialize (covers the enum-completeness path via a full circuit).
/// Fails pre-fix: OhmaticCircuitV01 type absent.
#[test]
fn test_schema_rejects_unknown_component_type_json() {
    let bad_circuit = r#"{
        "metadata": {
            "title": "Bad Type",
            "description": "unknown component type",
            "version": "0.1",
            "tags": ["test"]
        },
        "components": [
            {
                "id": "X1",
                "type": "unknown_widget",
                "value": "N/A",
                "part": "N/A",
                "x": 10.0,
                "y": 10.0,
                "pins": {"1": "1"}
            }
        ],
        "nets": [
            {"name": "GND", "pins": ["X1.1", "GND1.1"]}
        ]
    }"#;
    let result: Result<OhmaticCircuitV01, _> = serde_json::from_str(bad_circuit);
    assert!(
        result.is_err(),
        "circuit with 'unknown_widget' component type should be rejected by serde"
    );
}

/// AC5 — Every element in `dataset/examples.json` must have `tier3_reviewed: true`
/// at root level.
/// Fails pre-fix: `include_str!` compile error if file absent; assertion fails if
/// the field is missing on any circuit.
#[test]
fn test_examples_json_all_tier3_annotated() {
    let raw = include_str!("../../../dataset/examples.json");
    let examples: Vec<serde_json::Value> =
        serde_json::from_str(raw).expect("dataset/examples.json must be a valid JSON array");

    assert!(
        !examples.is_empty(),
        "dataset/examples.json must contain at least one circuit"
    );

    for (i, circuit) in examples.iter().enumerate() {
        let tier3 = circuit.get("tier3_reviewed");
        assert!(
            tier3.is_some(),
            "circuit at index {i} is missing 'tier3_reviewed' field"
        );
        assert_eq!(
            tier3.unwrap(),
            &serde_json::Value::Bool(true),
            "circuit at index {i} has 'tier3_reviewed' != true (got {:?})",
            tier3.unwrap()
        );
    }
}

/// AC7 — `shared/docs/contracts.md` must contain all five endpoint strings and
/// the versioning dispatch sentinel `unsupported_schema_version`.
/// Fails pre-fix: `include_str!` compile error if file absent.
#[test]
fn test_contracts_md_contains_all_endpoints() {
    let text = include_str!("../../../shared/docs/contracts.md");

    let required_strings = [
        "POST /v1/generate",
        "GET /v1/jobs/{id}/status",
        "POST /infer",
        "POST /verify",
        "POST /enrich",
        "unsupported_schema_version",
    ];

    for s in &required_strings {
        assert!(
            text.contains(s),
            "contracts.md does not contain required string: '{s}'"
        );
    }
}

/// AC6 — `shared/docs/log_schema.md` must document all five required log fields.
/// Fails pre-fix: `include_str!` compile error if file absent.
#[test]
fn test_log_schema_md_has_required_fields() {
    let text = include_str!("../../../shared/docs/log_schema.md");

    let required_fields = ["timestamp", "request_id", "service", "level", "message"];

    for field in &required_fields {
        assert!(
            text.contains(field),
            "log_schema.md does not document required field: '{field}'"
        );
    }
}

/// AC7 — The done-state circuit shape referenced in contracts.md must deserialize
/// successfully as OhmaticCircuitV01.  This uses a hardcoded JSON literal that
/// matches the circuit shape shown in the contracts.md `/infer` response example.
/// Fails pre-fix: OhmaticCircuitV01 type absent.
#[test]
fn test_contracts_done_state_circuit_validates() {
    // Matches the circuit shape shown in contracts.md section 3 (POST /infer)
    let done_state_circuit = r#"{
        "metadata": {
            "title": "555 Timer Astable",
            "description": "Astable 555 timer generating 1 Hz square wave for LED blink",
            "version": "0.1",
            "tags": ["timer"]
        },
        "components": [
            {
                "id": "VCC1",
                "type": "power_vcc",
                "value": "9V",
                "part": "VCC",
                "x": 10.0,
                "y": 10.0,
                "pins": {"1": "VCC"}
            },
            {
                "id": "GND1",
                "type": "power_gnd",
                "value": "",
                "part": "GND",
                "x": 10.0,
                "y": 200.0,
                "pins": {"1": "GND"}
            },
            {
                "id": "U1",
                "type": "ic_timer",
                "value": "NE555",
                "part": "DIP-8",
                "x": 150.0,
                "y": 100.0,
                "pins": {"1": "GND", "2": "TRIG", "3": "OUT", "4": "RST", "5": "CV", "6": "THR", "7": "DIS", "8": "VCC"}
            },
            {
                "id": "R1",
                "type": "resistor",
                "value": "10kΩ",
                "part": "0603",
                "x": 80.0,
                "y": 60.0,
                "pins": {"1": "VCC", "2": "DIS"}
            },
            {
                "id": "LED1",
                "type": "led",
                "value": "RED",
                "part": "LED-3MM",
                "x": 230.0,
                "y": 100.0,
                "pins": {"A": "OUT", "K": "LED_K"}
            },
            {
                "id": "R2",
                "type": "resistor",
                "value": "330Ω",
                "part": "0603",
                "x": 270.0,
                "y": 100.0,
                "pins": {"1": "LED_K", "2": "GND"}
            }
        ],
        "nets": [
            {"name": "VCC",    "pins": ["VCC1.1", "U1.8", "R1.1"]},
            {"name": "DIS",    "pins": ["R1.2",   "U1.7", "U1.6", "U1.2"]},
            {"name": "OUT",    "pins": ["U1.3",   "LED1.A"]},
            {"name": "LED_K",  "pins": ["LED1.K", "R2.1"]},
            {"name": "GND",    "pins": ["GND1.1", "U1.1", "R2.2"]}
        ]
    }"#;

    let result: Result<OhmaticCircuitV01, _> = serde_json::from_str(done_state_circuit);
    assert!(
        result.is_ok(),
        "done-state circuit from contracts.md should deserialize as OhmaticCircuitV01: {:?}",
        result.err()
    );

    let circuit = result.unwrap();
    assert_eq!(circuit.metadata.version, "0.1");
    assert_eq!(circuit.metadata.title, "555 Timer Astable");
    assert_eq!(circuit.components.len(), 6);
    assert_eq!(circuit.nets.len(), 5);
}

/// Validates the done-state circuit from contracts.md against the compiled JSON Schema
/// (not just serde deserialization). Ensures schema-level constraints are satisfied.
#[test]
fn test_contracts_done_state_circuit_validates_against_json_schema() {
    use jsonschema::JSONSchema;

    let schema_str = include_str!("../../../shared/schema/circuit_v01.json");
    let schema_value: serde_json::Value =
        serde_json::from_str(schema_str).expect("circuit_v01.json must be valid JSON");
    let compiled = JSONSchema::compile(&schema_value).expect("schema compile failed");

    let done_state: serde_json::Value = serde_json::from_str(r#"{
        "metadata": {
            "title": "555 Timer Astable",
            "description": "Astable 555 timer generating 1 Hz square wave for LED blink",
            "version": "0.1",
            "tags": ["timer"]
        },
        "components": [
            {"id": "VCC1", "type": "power_vcc", "value": "9V", "part": "VCC",
             "x": 10.0, "y": 10.0, "pins": {"1": "VCC"}},
            {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
             "x": 10.0, "y": 200.0, "pins": {"1": "GND"}},
            {"id": "U1", "type": "ic_timer", "value": "NE555", "part": "DIP-8",
             "x": 150.0, "y": 100.0,
             "pins": {"1": "GND", "2": "TRIG", "3": "OUT", "4": "RST",
                      "5": "CV", "6": "THR", "7": "DIS", "8": "VCC"}},
            {"id": "R1", "type": "resistor", "value": "10kΩ", "part": "0603",
             "x": 80.0, "y": 60.0, "pins": {"1": "VCC", "2": "DIS"}},
            {"id": "LED1", "type": "led", "value": "RED", "part": "LED-3MM",
             "x": 230.0, "y": 100.0, "pins": {"A": "OUT", "K": "LED_K"}},
            {"id": "R2", "type": "resistor", "value": "330Ω", "part": "0603",
             "x": 270.0, "y": 100.0, "pins": {"1": "LED_K", "2": "GND"}}
        ],
        "nets": [
            {"name": "VCC",   "pins": ["VCC1.1", "U1.8", "R1.1"]},
            {"name": "DIS",   "pins": ["R1.2",   "U1.7", "U1.6", "U1.2"]},
            {"name": "OUT",   "pins": ["U1.3",   "LED1.A"]},
            {"name": "LED_K", "pins": ["LED1.K", "R2.1"]},
            {"name": "GND",   "pins": ["GND1.1", "U1.1", "R2.2"]}
        ]
    }"#).expect("test JSON must be valid");

    assert!(
        compiled.is_valid(&done_state),
        "done-state circuit must pass JSON Schema validation"
    );
}

// ---------------------------------------------------------------------------
// Round 1 triage tests — VALID findings (findings 1–7)
// ---------------------------------------------------------------------------

/// Finding 2 — Component pins values are typed as string in the schema and in
/// the Rust type (`HashMap<String, String>`). Deserializing a component whose
/// pin value is an integer (not a string) must fail at the serde layer.
#[test]
fn test_component_pin_integer_value_rejected_by_serde() {
    // Pin "1" has value 42 (integer) instead of a string — must be rejected.
    let bad_component = r#"{
        "id": "R1",
        "type": "resistor",
        "value": "10kΩ",
        "part": "0603",
        "x": 50.0,
        "y": 50.0,
        "pins": {"1": 42, "2": "2"}
    }"#;
    let result: Result<Component, _> = serde_json::from_str(bad_component);
    assert!(
        result.is_err(),
        "Component with integer pin value should be rejected by serde (pins is HashMap<String,String>)"
    );
}

/// Finding 3 — `nets[].pins` items must match `^[A-Z][A-Za-z0-9_]*\\.[A-Za-z0-9_]+$`.
/// A pin reference like "R1" (no dot, no pin name) must fail JSON Schema validation.
#[test]
fn test_net_pin_missing_dot_rejected_by_schema() {
    use jsonschema::JSONSchema;

    let schema_str = include_str!("../../../shared/schema/circuit_v01.json");
    let schema_value: serde_json::Value =
        serde_json::from_str(schema_str).expect("circuit_v01.json must be valid JSON");
    let compiled = JSONSchema::compile(&schema_value).expect("schema compile failed");

    // "R1" has no dot — does not satisfy the pattern `^[A-Z][A-Za-z0-9_]*\.[A-Za-z0-9_]+$`
    let instance: serde_json::Value = serde_json::from_str(r#"{
        "metadata": {
            "title": "Bad Pin Ref",
            "description": "net pin with no dot separator",
            "version": "0.1",
            "tags": ["test"]
        },
        "components": [
            {
                "id": "R1",
                "type": "resistor",
                "value": "10kΩ",
                "part": "0603",
                "x": 50.0,
                "y": 50.0,
                "pins": {"1": "VCC", "2": "GND"}
            },
            {
                "id": "VCC1",
                "type": "power_vcc",
                "value": "5V",
                "part": "VCC",
                "x": 10.0,
                "y": 10.0,
                "pins": {"1": "VCC"}
            },
            {
                "id": "GND1",
                "type": "power_gnd",
                "value": "",
                "part": "GND",
                "x": 90.0,
                "y": 90.0,
                "pins": {"1": "GND"}
            }
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "R1"]},
            {"name": "GND", "pins": ["R1.2", "GND1.1"]}
        ]
    }"#)
    .unwrap();

    assert!(
        !compiled.is_valid(&instance),
        "expected schema rejection for net pin reference 'R1' (missing dot separator)"
    );
}

/// Finding 4 — Component `id` pattern tightened to `^[A-Z][A-Za-z0-9_]*$`
/// (must start with uppercase letter, leading underscore no longer allowed).
///
/// Sub-test A: `"_bypass"` (leading underscore) must fail JSON Schema validation.
/// Sub-test B: `"C_bypass"` (uppercase first letter, underscore later) must still
/// pass serde deserialization — confirming the existing test_underscore_id_in_component
/// remains valid under the tightened pattern.
#[test]
fn test_leading_underscore_id_rejected_by_schema() {
    use jsonschema::JSONSchema;

    let schema_str = include_str!("../../../shared/schema/circuit_v01.json");
    let schema_value: serde_json::Value =
        serde_json::from_str(schema_str).expect("circuit_v01.json must be valid JSON");
    let compiled = JSONSchema::compile(&schema_value).expect("schema compile failed");

    // Sub-test A: "_bypass" starts with underscore — violates ^[A-Z][A-Za-z0-9_]*$
    let instance_bad: serde_json::Value = serde_json::from_str(r#"{
        "metadata": {
            "title": "Bad ID",
            "description": "component id with leading underscore",
            "version": "0.1",
            "tags": ["test"]
        },
        "components": [
            {
                "id": "_bypass",
                "type": "capacitor",
                "value": "100nF",
                "part": "0402",
                "x": 10.0,
                "y": 10.0,
                "pins": {"1": "VCC", "2": "GND"}
            },
            {
                "id": "VCC1",
                "type": "power_vcc",
                "value": "5V",
                "part": "VCC",
                "x": 10.0,
                "y": 5.0,
                "pins": {"1": "VCC"}
            },
            {
                "id": "GND1",
                "type": "power_gnd",
                "value": "",
                "part": "GND",
                "x": 10.0,
                "y": 50.0,
                "pins": {"1": "GND"}
            }
        ],
        "nets": [
            {"name": "VCC",  "pins": ["VCC1.1", "_bypass.1"]},
            {"name": "GND",  "pins": ["GND1.1", "_bypass.2"]}
        ]
    }"#)
    .unwrap();

    assert!(
        !compiled.is_valid(&instance_bad),
        "expected schema rejection for component id '_bypass' (leading underscore violates ^[A-Z] pattern)"
    );

    // Sub-test B: "C_bypass" passes serde (uppercase first letter is fine)
    let mut pins = HashMap::new();
    pins.insert("1".to_string(), "VCC".to_string());
    pins.insert("2".to_string(), "GND".to_string());
    let component = Component {
        id: "C_bypass".to_string(),
        component_type: ComponentType::Capacitor,
        value: "100nF".to_string(),
        part: "0402".to_string(),
        x: 10.0,
        y: 10.0,
        pins,
    };
    let json = serde_json::to_string(&component).expect("serialization failed");
    let restored: Component = serde_json::from_str(&json).expect("deserialization failed");
    assert_eq!(
        restored.id, "C_bypass",
        "C_bypass (uppercase C) must still pass serde deserialization under tightened pattern"
    );
}

/// Findings 1 & 5 — No duplicate net names within any circuit in examples.json.
/// Finding 1 specifically checks that the LDO circuit (index 7) has exactly one GND net.
/// Finding 5 generalises: all circuits in examples.json must have unique net names.
#[test]
fn test_examples_json_no_duplicate_net_names() {
    let raw = include_str!("../../../dataset/examples.json");
    let examples: Vec<serde_json::Value> =
        serde_json::from_str(raw).expect("dataset/examples.json must be a valid JSON array");

    assert!(
        !examples.is_empty(),
        "dataset/examples.json must contain at least one circuit"
    );

    for (i, circuit) in examples.iter().enumerate() {
        let nets = circuit
            .get("nets")
            .and_then(|n| n.as_array())
            .unwrap_or_else(|| panic!("circuit at index {i} has no 'nets' array"));

        let mut seen_names: std::collections::HashSet<&str> = std::collections::HashSet::new();
        for net in nets {
            let name = net
                .get("name")
                .and_then(|n| n.as_str())
                .unwrap_or_else(|| panic!("circuit at index {i} has a net with no 'name' field"));
            assert!(
                seen_names.insert(name),
                "circuit at index {i} (title: {:?}) has duplicate net name: '{name}'",
                circuit
                    .get("metadata")
                    .and_then(|m| m.get("title"))
                    .and_then(|t| t.as_str())
                    .unwrap_or("<unknown>")
            );
        }
    }
}

/// Finding 6 — `shared/docs/contracts.md` must contain an error.code table with
/// all five defined error codes. These are the authoritative strings consumed by
/// the gateway and by client error-handling code.
#[test]
fn test_contracts_md_contains_all_error_codes() {
    let text = include_str!("../../../shared/docs/contracts.md");

    let required_error_codes = [
        "tier1_validation_failed",
        "tier2_validation_failed",
        "grammar_timeout",
        "unsupported_schema_version",
        "inference_unavailable",
    ];

    for code in &required_error_codes {
        assert!(
            text.contains(code),
            "contracts.md does not contain required error.code: '{code}'"
        );
    }
}

/// Finding 7 — `shared/docs/log_schema.md` documents the ULID format for
/// `request_id`. The inline ULID example must be exactly 26 characters long,
/// consistent with the ULID specification.
#[test]
fn test_log_schema_md_ulid_example_is_26_chars() {
    let text = include_str!("../../../shared/docs/log_schema.md");

    // The normative ULID example is given inside backtick-quoted text:
    // Format: 26-char ULID, e.g. `"01HWABCDE1234567890ABCDEF0"`.
    // Extract the first ULID-like token (all-caps alphanumeric, ≈26 chars)
    // by finding the substring between the `"` markers after "e.g.".
    let eg_marker = "e.g. `\"";
    let start = text
        .find(eg_marker)
        .unwrap_or_else(|| panic!("log_schema.md missing 'e.g. `\"' marker for ULID example"));
    let after_marker = &text[start + eg_marker.len()..];
    let end = after_marker
        .find('"')
        .unwrap_or_else(|| panic!("log_schema.md ULID example not terminated with '\"'"));
    let ulid_example = &after_marker[..end];

    assert_eq!(
        ulid_example.len(),
        26,
        "ULID example in log_schema.md must be 26 characters; found '{}' ({} chars)",
        ulid_example,
        ulid_example.len()
    );
}

// ---------------------------------------------------------------------------
// Round 2 constraint tests — uniqueItems on tags, minLength on tag items,
// uniqueItems on nets[].pins
// ---------------------------------------------------------------------------

/// Round 2 — tags minLength: 1 constraint; an empty-string tag must fail JSON Schema validation.
#[test]
fn test_empty_tag_rejected_by_schema() {
    use jsonschema::JSONSchema;

    let schema_str = include_str!("../../../shared/schema/circuit_v01.json");
    let schema_value: serde_json::Value =
        serde_json::from_str(schema_str).expect("circuit_v01.json must be valid JSON");
    let compiled = JSONSchema::compile(&schema_value).expect("schema compile failed");

    let instance: serde_json::Value = serde_json::from_str(r#"{
        "metadata": {
            "title": "Test",
            "description": "test",
            "version": "0.1",
            "tags": [""]
        },
        "components": [
            {
                "id": "VCC1",
                "type": "power_vcc",
                "value": "5V",
                "part": "VCC",
                "x": 10.0,
                "y": 10.0,
                "pins": {"1": "VCC"}
            },
            {
                "id": "GND1",
                "type": "power_gnd",
                "value": "",
                "part": "GND",
                "x": 10.0,
                "y": 50.0,
                "pins": {"1": "GND"}
            }
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "GND1.1"]}
        ]
    }"#)
    .expect("test JSON must be valid");

    assert!(
        !compiled.is_valid(&instance),
        "expected schema rejection for empty-string tag (violates minLength: 1)"
    );
}

/// Round 2 — tags uniqueItems constraint; duplicate tags must fail JSON Schema validation.
#[test]
fn test_duplicate_tags_rejected_by_schema() {
    use jsonschema::JSONSchema;

    let schema_str = include_str!("../../../shared/schema/circuit_v01.json");
    let schema_value: serde_json::Value =
        serde_json::from_str(schema_str).expect("circuit_v01.json must be valid JSON");
    let compiled = JSONSchema::compile(&schema_value).expect("schema compile failed");

    let instance: serde_json::Value = serde_json::from_str(r#"{
        "metadata": {
            "title": "Test",
            "description": "test",
            "version": "0.1",
            "tags": ["timer", "timer"]
        },
        "components": [
            {
                "id": "VCC1",
                "type": "power_vcc",
                "value": "5V",
                "part": "VCC",
                "x": 10.0,
                "y": 10.0,
                "pins": {"1": "VCC"}
            },
            {
                "id": "GND1",
                "type": "power_gnd",
                "value": "",
                "part": "GND",
                "x": 10.0,
                "y": 50.0,
                "pins": {"1": "GND"}
            }
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "GND1.1"]}
        ]
    }"#)
    .expect("test JSON must be valid");

    assert!(
        !compiled.is_valid(&instance),
        "expected schema rejection for duplicate tags [\"timer\", \"timer\"] (violates uniqueItems: true)"
    );
}

/// Round 2 — nets[].pins uniqueItems constraint; duplicate pin refs in one net must fail JSON Schema validation.
#[test]
fn test_duplicate_net_pin_ref_rejected_by_schema() {
    use jsonschema::JSONSchema;

    let schema_str = include_str!("../../../shared/schema/circuit_v01.json");
    let schema_value: serde_json::Value =
        serde_json::from_str(schema_str).expect("circuit_v01.json must be valid JSON");
    let compiled = JSONSchema::compile(&schema_value).expect("schema compile failed");

    let instance: serde_json::Value = serde_json::from_str(r#"{
        "metadata": {
            "title": "Test",
            "description": "test",
            "version": "0.1",
            "tags": ["test"]
        },
        "components": [
            {
                "id": "VCC1",
                "type": "power_vcc",
                "value": "5V",
                "part": "VCC",
                "x": 10.0,
                "y": 10.0,
                "pins": {"1": "VCC"}
            },
            {
                "id": "GND1",
                "type": "power_gnd",
                "value": "",
                "part": "GND",
                "x": 10.0,
                "y": 50.0,
                "pins": {"1": "GND"}
            }
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "VCC1.1"]},
            {"name": "GND", "pins": ["VCC1.1", "GND1.1"]}
        ]
    }"#)
    .expect("test JSON must be valid");

    assert!(
        !compiled.is_valid(&instance),
        "expected schema rejection for duplicate pin refs [\"VCC1.1\", \"VCC1.1\"] in one net (violates uniqueItems: true)"
    );
}
