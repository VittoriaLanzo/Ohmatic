//! Ohmatic verifier - public library surface.
//!
//! Exposes [`create_app`] (the axum Router) and [`BBOX_TOML`] (the embedded
//! component registry) so integration tests and the binary entry-point can
//! share the same initialisation path.

pub mod config;
pub mod drc;

pub static BBOX_TOML: &str = include_str!("../config/component_registry.toml");

use std::sync::Arc;

use axum::{
    extract::{State, Request},
    http::StatusCode,
    response::Json,
    routing::{get, post},
    Router,
};
use ohmatic_types::OhmaticCircuitV01;
use serde_json::{json, Value};

#[derive(Clone)]
struct AppState {
    bboxes: Arc<config::BboxConfig>,
}

pub fn create_app(bboxes: Arc<config::BboxConfig>) -> Router {
    let state = AppState { bboxes };
    Router::new()
        .route("/health", get(health_handler))
        .route("/verify", post(verify_handler))
        .with_state(state)
}

async fn health_handler() -> Json<Value> {
    Json(json!({"status": "ok"}))
}

async fn verify_handler(
    State(state): State<AppState>,
    req: Request,
) -> (StatusCode, Json<Value>) {
    // Extract raw bytes from the request body - cap at 1 MiB to prevent memory exhaustion DoS.
    const MAX_BODY_BYTES: usize = 1_048_576; // 1 MiB
    let body_bytes = match axum::body::to_bytes(req.into_body(), MAX_BODY_BYTES).await {
        Ok(b) => b,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "request body too large (max 1 MiB)"})),
            );
        }
    };

    // Step 1: parse body to JSON Value
    if body_bytes.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "missing 'circuit' field"})),
        );
    }
    let body_value: Value = match serde_json::from_slice(&body_bytes) {
        Ok(v) => v,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "missing 'circuit' field"})),
            );
        }
    };

    // Step 2: extract "circuit" field - must be present and non-null.
    let circuit_value = match body_value.get("circuit") {
        Some(v) if !v.is_null() => v.clone(),
        Some(_) => {
            // circuit field is null → treat same as missing
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "missing 'circuit' field"})),
            );
        }
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "missing 'circuit' field"})),
            );
        }
    };

    // Step 3: deserialise into OhmaticCircuitV01.
    // T1-PARSE-SERDE: JSON structure is valid but cannot be coerced into OhmaticCircuitV01
    // (missing required field, wrong type, deny_unknown_fields violation on Component/Net).
    let circuit: OhmaticCircuitV01 = match serde_json::from_value(circuit_value) {
        Ok(c) => c,
        Err(e) => {
            return (
                StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({
                    "errors": [format!("[T1-PARSE-SERDE] failed to deserialise circuit: {}", e)],
                    "warnings": []
                })),
            );
        }
    };

    // Step 3b: validate all component types against the registry.
    // T1-PARSE-REGISTRY: type string is valid JSON but not in the known component registry.
    // Distinct from T1-PARSE-SERDE so the gateway can distinguish "model hallucinated a type"
    // (retry-able) from "JSON was malformed" (not retry-able).
    let unknown_type_errors: Vec<String> = circuit.components.iter()
        .filter(|c| !state.bboxes.components.contains_key(c.component_type.as_str()))
        .map(|c| format!("[T1-PARSE-REGISTRY] unknown component type '{}' on component '{}'",
                         c.component_type, c.id))
        .collect();
    if !unknown_type_errors.is_empty() {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "errors": unknown_type_errors,
                "warnings": []
            })),
        );
    }

    // Step 4: Tier 1 schema rules
    if let Err(errs) = drc::schema_rules::run_tier1(&circuit) {
        let error_strs: Vec<String> = errs.iter().map(|e| e.to_wire()).collect();
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({
                "errors": error_strs,
                "warnings": []
            })),
        );
    }

    // Step 5: Tier 2 geometry correction
    let (modified_comps, t2_warnings) = drc::corrector::run_tier2(&circuit, &state.bboxes);

    // Rebuild circuit with corrected components
    let normalized_circuit = OhmaticCircuitV01 {
        metadata: circuit.metadata.clone(),
        components: modified_comps,
        nets: circuit.nets.clone(),
    };

    // Step 6: Tier 3 electrical rules
    let t3_warnings = drc::electrical_rules::run_tier3(&normalized_circuit);

    // Collect all warnings
    let mut all_warnings: Vec<String> = t2_warnings.iter().map(|w| w.to_wire()).collect();
    all_warnings.extend(t3_warnings.iter().map(|w| w.to_wire()));

    // Step 7: 200 response
    (
        StatusCode::OK,
        Json(json!({
            "circuit": serde_json::to_value(&normalized_circuit)
                           .expect("OhmaticCircuitV01 must be serialisable to JSON"),
            "warnings": all_warnings,
            "errors": []
        })),
    )
}
