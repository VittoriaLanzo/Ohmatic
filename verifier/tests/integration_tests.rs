use axum_test::TestServer;
use serde_json::{json, Value};
use std::sync::Arc;

fn make_server() -> TestServer {
    let bboxes = Arc::new(
        verifier::config::BboxConfig::load_from_str(verifier::BBOX_TOML)
            .expect("embedded component_registry.toml must parse"),
    );
    TestServer::new(verifier::create_app(bboxes)).unwrap()
}

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------

#[tokio::test]
async fn health_returns_ok() {
    let server = make_server();
    let resp = server.get("/health").await;
    resp.assert_status_ok();
    let body: Value = resp.json();
    assert_eq!(body, json!({"status": "ok"}));
}

// ---------------------------------------------------------------------------
// Category A — all seed circuits return 200
// ---------------------------------------------------------------------------

#[tokio::test]
async fn seed_circuits_all_return_200() {
    let server = make_server();
    let manifest = env!("CARGO_MANIFEST_DIR");
    let path = std::path::Path::new(manifest).join("../dataset/examples.json");
    let raw = std::fs::read_to_string(&path).unwrap();
    let circuits: Vec<Value> = serde_json::from_str(&raw).unwrap();
    for (i, circuit) in circuits.iter().enumerate() {
        let body = json!({"circuit": circuit});
        let resp = server.post("/verify").json(&body).await;
        assert_eq!(
            resp.status_code(),
            200,
            "circuit #{} should return 200, got {}",
            i,
            resp.status_code()
        );
    }
}

// ---------------------------------------------------------------------------
// Category B — T1 violations → 422
// ---------------------------------------------------------------------------

// Helper: minimal valid circuit body suitable for modification.
// Components: VCC1 (power_vcc), GND1 (power_gnd), R1 (resistor, 2-pin).
// Nets: VCC [VCC1.1, R1.1], GND [GND1.1, R1.2].
fn minimal_valid_circuit() -> Value {
    json!({
        "metadata": {
            "title": "Test Circuit",
            "description": "Minimal valid circuit for testing",
            "version": "0.1",
            "tags": ["test"]
        },
        "components": [
            {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
             "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
            {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
             "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
            {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
             "x": 5.0, "y": 0.0, "pins": {"1": "vcc_r", "2": "gnd_r"}}
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
            {"name": "GND", "pins": ["GND1.1", "R1.2"]}
        ]
    })
}

#[tokio::test]
async fn t1_parse_unknown_component_type_422() {
    let server = make_server();
    // "unknown_widget" is not in the component registry — the verifier rejects it as T1-PARSE.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "T",
                "description": "d",
                "version": "0.1",
                "tags": ["t"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "v"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "g"}},
                {"id": "X1", "type": "unknown_widget", "value": "", "part": "",
                 "x": 5.0, "y": 0.0, "pins": {"1": "v", "2": "g"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "X1.1"]},
                {"name": "GND", "pins": ["GND1.1", "X1.2"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 422);
    let r: Value = resp.json();
    let errors = r["errors"].as_array().unwrap();
    assert!(!errors.is_empty());
    assert!(
        errors[0].as_str().unwrap().starts_with("[T1-PARSE]"),
        "expected [T1-PARSE], got: {}",
        errors[0]
    );
}

#[tokio::test]
async fn t1_01_wrong_version_422() {
    let server = make_server();
    let mut circuit = minimal_valid_circuit();
    circuit["metadata"]["version"] = json!("0.99");
    let body = json!({"circuit": circuit});
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 422);
    let r: Value = resp.json();
    let errors = r["errors"].as_array().unwrap();
    assert!(
        errors.iter().any(|e| e.as_str().unwrap_or("").starts_with("[T1-01]")),
        "expected a [T1-01] error, got: {:?}",
        errors
    );
}

#[tokio::test]
async fn t1_04_duplicate_id_422() {
    let server = make_server();
    // Two components both with id "R1" — duplicate ID violation.
    // Nets reference R1.1 and R1.2 (valid pin names on R1, which has pins 1 and 2).
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Dup ID Test",
                "description": "Duplicate component ID",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 5.0, "y": 0.0, "pins": {"1": "a", "2": "b"}},
                {"id": "R1", "type": "resistor", "value": "1k", "part": "RES",
                 "x": 20.0, "y": 0.0, "pins": {"1": "a", "2": "b"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 422);
    let r: Value = resp.json();
    let errors = r["errors"].as_array().unwrap();
    assert!(
        errors.iter().any(|e| e.as_str().unwrap_or("").starts_with("[T1-04]")),
        "expected a [T1-04] error, got: {:?}",
        errors
    );
}

#[tokio::test]
async fn t1_05_no_vcc_422() {
    let server = make_server();
    // Replace VCC1 with another resistor R2 — no power_vcc present.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "No VCC",
                "description": "Missing power_vcc",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "R2", "type": "resistor", "value": "1k", "part": "RES",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc_side"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 5.0, "y": 0.0, "pins": {"1": "vcc_side", "2": "gnd"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["R2.1", "R1.1"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 422);
    let r: Value = resp.json();
    let errors = r["errors"].as_array().unwrap();
    assert!(
        errors.iter().any(|e| e.as_str().unwrap_or("").starts_with("[T1-05]")),
        "expected a [T1-05] error, got: {:?}",
        errors
    );
}

#[tokio::test]
async fn t1_06_net_one_pin_422() {
    let server = make_server();
    // VCC net with only 1 pin reference.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Single Pin Net",
                "description": "Net with only 1 pin",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 5.0, "y": 0.0, "pins": {"1": "a", "2": "b"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1"]},
                {"name": "MID", "pins": ["R1.1", "R1.2"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 422);
    let r: Value = resp.json();
    let errors = r["errors"].as_array().unwrap();
    assert!(
        errors.iter().any(|e| e.as_str().unwrap_or("").starts_with("[T1-06]")),
        "expected a [T1-06] error, got: {:?}",
        errors
    );
}

#[tokio::test]
async fn t1_07_unknown_ref_422() {
    let server = make_server();
    // A net references "FAKE" — component that doesn't exist.
    // We need FAKE.1 to have a valid format (starts with uppercase letter).
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Unknown Ref",
                "description": "Net references unknown component",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 5.0, "y": 0.0, "pins": {"1": "a", "2": "b"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2"]},
                {"name": "ORPHAN", "pins": ["FAKE.1", "VCC1.1"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 422);
    let r: Value = resp.json();
    let errors = r["errors"].as_array().unwrap();
    assert!(
        errors.iter().any(|e| e.as_str().unwrap_or("").starts_with("[T1-07]")),
        "expected a [T1-07] error, got: {:?}",
        errors
    );
}

// ---------------------------------------------------------------------------
// Category B — T2 tests → 200 with warnings
// ---------------------------------------------------------------------------

#[tokio::test]
async fn t2_01_out_of_range_normalised_200() {
    let server = make_server();
    // x=1000 is out of 0-300 range — normalisation fires → T2-01 warning.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Out Of Range",
                "description": "Coordinates outside canvas",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 1000.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 500.0, "y": 0.0, "pins": {"1": "vcc_side", "2": "gnd_side"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T2 must return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T2-01]")),
        "expected a [T2-01] warning, got: {:?}",
        warnings
    );
}

#[tokio::test]
async fn t2_02_unresolvable_collision_200() {
    let server = make_server();
    // 3 resistors all at (50, 50) — packed collision, at least one pair will
    // still collide after correction. T2 never returns 422 regardless.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Collision Test",
                "description": "Multiple components at same position",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 50.0, "y": 50.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 50.0, "y": 50.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 50.0, "y": 50.0, "pins": {"1": "vcc_side", "2": "gnd_side"}},
                {"id": "R2", "type": "resistor", "value": "1k", "part": "RES",
                 "x": 50.0, "y": 50.0, "pins": {"1": "vcc_side", "2": "gnd_side"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "R1.1", "R2.1"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2", "R2.2"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T2 must always return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    // Response must have circuit, warnings, errors fields
    assert!(r.get("circuit").is_some(), "response missing 'circuit' field");
    assert!(r.get("warnings").is_some(), "response missing 'warnings' field");
    assert!(r.get("errors").is_some(), "response missing 'errors' field");
}

// ---------------------------------------------------------------------------
// Category B — T3 tests → 200 with warnings containing the rule ID
// ---------------------------------------------------------------------------

#[tokio::test]
async fn t3_01_short_circuit_200_with_warning() {
    let server = make_server();
    // VCC1 and GND1 both on "SHORT" net, R1 pins also on SHORT.
    // All component pins appear in exactly one net → T1 passes.
    // T3-01 fires because VCC and GND share the same net.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Short Circuit",
                "description": "VCC and GND directly connected",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "s"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "s"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 5.0, "y": 0.0, "pins": {"1": "s", "2": "s"}}
            ],
            "nets": [
                {"name": "SHORT", "pins": ["VCC1.1", "GND1.1", "R1.1", "R1.2"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200,
        "short circuit should return 200 (T3 never 422), got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T3-01]")),
        "expected a [T3-01] warning, got: {:?}",
        warnings
    );
}

#[tokio::test]
async fn t3_02_led_no_resistor_200_with_warning() {
    let server = make_server();
    // LED anode directly on VCC, no current-limiting resistor.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "LED No Resistor",
                "description": "LED without current limiting resistor",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "LED1", "type": "led", "value": "red", "part": "LED",
                 "x": 5.0, "y": 0.0, "pins": {"A": "vcc", "K": "gnd"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "LED1.A"]},
                {"name": "GND", "pins": ["GND1.1", "LED1.K"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T3 must return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T3-02]")),
        "expected a [T3-02] warning, got: {:?}",
        warnings
    );
}

#[tokio::test]
async fn t3_03_floating_mosfet_gate_200_with_warning() {
    let server = make_server();
    // MOSFET gate on a net with no driver/bias component.
    // Two MOSFETs share a gate net — neither qualifies as a driver for the other.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Floating MOSFET Gate",
                "description": "MOSFET gate with no driver",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "Q1", "type": "mosfet_n", "value": "2N7000", "part": "MOSFET",
                 "x": 5.0, "y": 0.0, "pins": {"G": "gate", "D": "vcc", "S": "gnd"}},
                {"id": "Q2", "type": "mosfet_n", "value": "2N7000", "part": "MOSFET",
                 "x": 15.0, "y": 0.0, "pins": {"G": "gate", "D": "vcc", "S": "gnd"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "Q1.D", "Q2.D"]},
                {"name": "GND", "pins": ["GND1.1", "Q1.S", "Q2.S"]},
                {"name": "GATE", "pins": ["Q1.G", "Q2.G"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T3 must return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T3-03]")),
        "expected a [T3-03] warning, got: {:?}",
        warnings
    );
}

#[tokio::test]
async fn t3_04_ic_no_bypass_cap_200_with_warning() {
    let server = make_server();
    // IC op-amp on VCC, no bypass capacitor.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "IC No Bypass Cap",
                "description": "IC without bypass capacitor",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "U1", "type": "ic_opamp", "value": "LM358", "part": "IC",
                 "x": 5.0, "y": 0.0, "pins": {"VCC": "vcc", "GND": "gnd", "OUT": "gnd"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "U1.VCC"]},
                {"name": "GND", "pins": ["GND1.1", "U1.GND", "U1.OUT"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T3 must return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T3-04]")),
        "expected a [T3-04] warning, got: {:?}",
        warnings
    );
}

#[tokio::test]
async fn t3_05_reversed_capacitor_200_with_warning() {
    let server = make_server();
    // Capacitor pin1 (positive) connected to GND — polarity reversed.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Reversed Cap",
                "description": "Capacitor with reversed polarity",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "C1", "type": "capacitor", "value": "100uF", "part": "CAP",
                 "x": 5.0, "y": 0.0, "pins": {"1": "gnd", "2": "vcc"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "C1.2"]},
                {"name": "GND", "pins": ["GND1.1", "C1.1"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T3 must return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T3-05]")),
        "expected a [T3-05] warning, got: {:?}",
        warnings
    );
}

#[tokio::test]
async fn t3_06_ic_no_vcc_pin_200_with_warning() {
    let server = make_server();
    // IC timer with no pin on the VCC net.
    // R1 bridges VCC→MID, U1 has GND and OUT (both on GND or MID), no VCC pin on U1.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "IC No VCC",
                "description": "IC with no pin on VCC net",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 3.0, "y": 0.0, "pins": {"1": "vcc", "2": "mid"}},
                {"id": "U1", "type": "ic_timer", "value": "NE555", "part": "IC",
                 "x": 5.0, "y": 0.0, "pins": {"GND": "gnd", "OUT": "mid"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
                {"name": "MID", "pins": ["R1.2", "U1.OUT"]},
                {"name": "GND", "pins": ["GND1.1", "U1.GND"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T3 must return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T3-06]")),
        "expected a [T3-06] warning, got: {:?}",
        warnings
    );
}

#[tokio::test]
async fn t3_07_isolated_component_200_with_warning() {
    let server = make_server();
    // R2 is isolated — not reachable from any power net via BFS.
    // But it still needs ≥1 net with ≥2 pins to pass T1.
    // We give R2 its own island net, and give that net 2 pins from R2.
    // Wait: R2 only has 2 pins, so R2.1 and R2.2 can share a net of 2 pins.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Isolated Component",
                "description": "Component not connected to power net",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 5.0, "y": 0.0, "pins": {"1": "vcc", "2": "gnd"}},
                {"id": "R2", "type": "resistor", "value": "1k", "part": "RES",
                 "x": 50.0, "y": 50.0, "pins": {"1": "isl_a", "2": "isl_b"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2"]},
                {"name": "ISLAND_A", "pins": ["R2.1", "R2.2"]}
            ]
        }
    });
    // R2.1 and R2.2 on ISLAND_A — both pins covered. But ISLAND_A is disconnected from
    // any power net. However R2.1 and R2.2 appear in only one net (ISLAND_A) — that's fine.
    // Wait: R2 has pins "1" and "2". ISLAND_A has R2.1 and R2.2 — both covered.
    // T1 validation requires: all component pins connected. R2.1 → ISLAND_A, R2.2 → ISLAND_A. OK.
    // ISLAND_A has 2 pins. OK. T1 passes. T3-07 should fire.
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T3 must return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T3-07]")),
        "expected a [T3-07] warning, got: {:?}",
        warnings
    );
}

#[tokio::test]
async fn t3_08_button_no_pullup_200_with_warning() {
    let server = make_server();
    // Two buttons share SIG net; no resistor on SIG → T3-08 fires.
    // R1 (VCC→GND) keeps T1 happy (provides the VCC net with 2 pins).
    // SW1 pin1→SIG, SW2 pin1→SIG: both on same net, no resistor present.
    let body = json!({
        "circuit": {
            "metadata": {
                "title": "Button No Pullup",
                "description": "Button without pull-up resistor",
                "version": "0.1",
                "tags": ["test"]
            },
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "x": 0.0, "y": 0.0, "pins": {"1": "vcc"}},
                {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
                 "x": 10.0, "y": 0.0, "pins": {"1": "gnd"}},
                {"id": "R1", "type": "resistor", "value": "10k", "part": "RES",
                 "x": 3.0, "y": 0.0, "pins": {"1": "vcc", "2": "gnd"}},
                {"id": "SW1", "type": "button", "value": "", "part": "BTN",
                 "x": 5.0, "y": 0.0, "pins": {"1": "sig", "2": "gnd"}},
                {"id": "SW2", "type": "button", "value": "", "part": "BTN",
                 "x": 8.0, "y": 0.0, "pins": {"1": "sig", "2": "gnd"}}
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2", "SW1.2", "SW2.2"]},
                {"name": "SIG", "pins": ["SW1.1", "SW2.1"]}
            ]
        }
    });
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 200, "T3 must return 200, got {}", resp.status_code());
    let r: Value = resp.json();
    let warnings = r["warnings"].as_array().unwrap();
    assert!(
        warnings.iter().any(|w| w.as_str().unwrap_or("").starts_with("[T3-08]")),
        "expected a [T3-08] warning, got: {:?}",
        warnings
    );
}

// ---------------------------------------------------------------------------
// Edge cases — empty body and missing 'circuit' field → 400
// ---------------------------------------------------------------------------

#[tokio::test]
async fn missing_circuit_field_400() {
    let server = make_server();
    let body = json!({"not_circuit": {}});
    let resp = server.post("/verify").json(&body).await;
    assert_eq!(resp.status_code(), 400);
    let r: Value = resp.json();
    assert_eq!(r["error"], json!("missing 'circuit' field"));
}
