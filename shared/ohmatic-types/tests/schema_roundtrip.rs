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
    let raw = include_str!("../../shared/schema/circuit_v01.json");
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
        schema_uri.contains("draft-07") || schema_uri.contains("json-schema.org"),
        "circuit_v01.json '$schema' does not reference a JSON Schema draft-07 URI: {schema_uri}"
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
    let raw = include_str!("../../dataset/examples.json");
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
    let text = include_str!("../../shared/docs/contracts.md");

    let required_strings = [
        "POST /v1/generate",
        "GET /v1/jobs",
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
    let text = include_str!("../../shared/docs/log_schema.md");

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
