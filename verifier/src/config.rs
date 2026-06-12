//! Component registry - loads `component_registry.toml` and provides
//! bounding-box and metadata lookups used by the Tier 2 geometry pipeline.

use std::collections::HashMap;
use std::path::Path;

use ohmatic_types::ComponentType;
use serde::Deserialize;

/// Metadata for a single component type in the registry.
#[derive(Debug, Clone, Deserialize)]
pub struct ComponentEntry {
    /// Bounding-box `[width, height]` in canvas units (used by Tier 2 collision detection).
    pub bbox: [f64; 2],
    /// Reference designator prefix (e.g. "R", "C", "U"). Informational only.
    pub ref_prefix: Option<String>,
    /// One-line human-readable description. Informational only.
    pub description: Option<String>,
}

/// Default values applied when a type is not listed in the registry.
#[derive(Debug, Clone, Deserialize)]
pub struct RegistryDefaults {
    pub bbox: [f64; 2],
}

/// Internal raw TOML shape - `defaults` section + every other key as a component entry.
#[derive(Debug, Clone, Deserialize)]
struct ComponentRegistryRaw {
    pub defaults: RegistryDefaults,
    #[serde(flatten)]
    pub components: HashMap<String, ComponentEntry>,
}

/// Component registry loaded from `component_registry.toml`.
///
/// Provides `get()` for bbox lookup (same API as the old BboxConfig)
/// and `entry()` for full metadata access.
#[derive(Debug, Clone)]
pub struct BboxConfig {
    pub components: HashMap<String, ComponentEntry>,
    pub default_bbox: [f64; 2],
}

impl BboxConfig {
    /// Look up bounding-box `(width, height)` for a given `ComponentType`.
    /// Falls back to the registry `[defaults]` bbox when the type is not listed.
    pub fn get(&self, ct: &ComponentType) -> (f64, f64) {
        if let Some(entry) = self.components.get(ct.as_str()) {
            (entry.bbox[0], entry.bbox[1])
        } else {
            (self.default_bbox[0], self.default_bbox[1])
        }
    }

    /// Look up the full `ComponentEntry` for a given `ComponentType`, if registered.
    pub fn entry(&self, ct: &ComponentType) -> Option<&ComponentEntry> {
        self.components.get(ct.as_str())
    }

    /// Parse a `component_registry.toml` string (e.g. from `include_str!`).
    pub fn load_from_str(content: &str) -> Result<BboxConfig, Box<dyn std::error::Error>> {
        let parsed: ComponentRegistryRaw = toml::from_str(content)?;
        Ok(BboxConfig {
            components: parsed.components,
            default_bbox: parsed.defaults.bbox,
        })
    }

    /// Load and parse a `component_registry.toml` file from `path`.
    pub fn load(path: &Path) -> Result<BboxConfig, Box<dyn std::error::Error>> {
        let raw = std::fs::read_to_string(path)?;
        Self::load_from_str(&raw)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    fn load_registry() -> BboxConfig {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("config/component_registry.toml");
        BboxConfig::load(&path).expect("component_registry.toml must parse")
    }

    #[test]
    fn registry_parses_and_all_entries_have_positive_bbox() {
        let config = load_registry();

        // Every entry in the registry must have positive bbox dimensions.
        // The registry is the single source of truth - no hardcoded type list to maintain.
        // To add a new type: add an entry to component_registry.toml; this test auto-covers it.
        assert!(
            config.components.len() >= 70,
            "registry must have at least 70 component types, found {}",
            config.components.len()
        );
        for (name, entry) in &config.components {
            assert!(entry.bbox[0] > 0.0, "'{}' width must be > 0", name);
            assert!(entry.bbox[1] > 0.0, "'{}' height must be > 0", name);
        }
        assert_eq!(config.default_bbox, [12.0, 12.0]);
    }

    #[test]
    fn get_returns_known_type() {
        let config = load_registry();
        let (w, h) = config.get(&ComponentType::new("resistor"));
        assert_eq!((w, h), (8.0, 4.0));
    }

    #[test]
    fn get_falls_back_for_unknown() {
        // BboxConfig with empty components map uses default_bbox for any unknown type.
        let config = BboxConfig {
            components: HashMap::new(),
            default_bbox: [12.0, 12.0],
        };
        let (w, h) = config.get(&ComponentType::new("unknown_widget"));
        assert_eq!((w, h), (12.0, 12.0));
    }

    #[test]
    fn entry_returns_full_metadata() {
        let config = load_registry();
        let entry = config.entry(&ComponentType::new("relay")).expect("relay must be registered");
        assert_eq!(entry.bbox, [16.0, 12.0]);
        assert_eq!(entry.ref_prefix.as_deref(), Some("K"));
    }
}
