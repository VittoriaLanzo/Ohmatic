//! `ohmatic-types` - shared circuit data model.
//!
//! Re-exports [`OhmaticCircuitV01`], [`Component`], [`ComponentType`],
//! [`component_types`] constants, [`Net`], and [`CircuitMetadata`].

pub mod circuit;
pub use circuit::{CircuitMetadata, Component, ComponentType, Net, OhmaticCircuitV01};
pub use circuit::component_types;
