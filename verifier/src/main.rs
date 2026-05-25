//! Verifier service entry-point.
//!
//! Binds `0.0.0.0:8002`, loads the embedded component registry, and serves
//! the axum Router produced by [`verifier::create_app`].

use std::sync::Arc;
use verifier::{create_app, BBOX_TOML};

#[tokio::main]
async fn main() {
    let bboxes = verifier::config::BboxConfig::load_from_str(BBOX_TOML)
        .expect("embedded component_registry.toml must parse");
    let listener = tokio::net::TcpListener::bind("0.0.0.0:8002")
        .await
        .expect("failed to bind TCP listener on 0.0.0.0:8002");
    axum::serve(listener, create_app(Arc::new(bboxes)))
        .await
        .expect("axum server exited unexpectedly");
}
