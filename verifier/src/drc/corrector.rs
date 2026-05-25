use crate::config::BboxConfig;
use crate::drc::collision::correct_collision;
use crate::drc::rule_ids::{T2_COLLISION, T2_NORMALISE};
use crate::drc::schema_rules::{DrcError, DrcLevel};
use crate::drc::spatial_hash::find_collisions;
use ohmatic_types::{Component, OhmaticCircuitV01};

pub const CANVAS_MAX: f64 = 300.0;

/// Normalise component coordinates to the 0–300 canvas.
/// If all coordinates are already within [0, CANVAS_MAX], returns the components unchanged
/// and an empty warnings list.
/// If any coordinate is outside [0, CANVAS_MAX], rescales ALL components proportionally
/// (preserving aspect ratio) and emits a T2-01 DRC_WARNING.
pub fn normalise_coordinates(
    components: &mut Vec<Component>,
    _bboxes: &BboxConfig,
) -> Vec<DrcError> {
    if components.is_empty() {
        return vec![];
    }

    let min_x = components.iter().map(|c| c.x).fold(f64::INFINITY, f64::min);
    let max_x = components.iter().map(|c| c.x).fold(f64::NEG_INFINITY, f64::max);
    let min_y = components.iter().map(|c| c.y).fold(f64::INFINITY, f64::min);
    let max_y = components.iter().map(|c| c.y).fold(f64::NEG_INFINITY, f64::max);

    // Check if everything is already in range.
    if min_x >= 0.0 && max_x <= CANVAS_MAX && min_y >= 0.0 && max_y <= CANVAS_MAX {
        return vec![];
    }

    // Shift so min is 0, then scale to fit CANVAS_MAX preserving aspect ratio.
    // For a single component (or all components at the same point), range is 0 — scale = 1.
    let range_x = max_x - min_x;
    let range_y = max_y - min_y;
    let max_range = range_x.max(range_y);

    let scale = if max_range > 0.0 {
        CANVAS_MAX / max_range
    } else {
        1.0
    };

    for comp in components.iter_mut() {
        comp.x = ((comp.x - min_x) * scale).min(CANVAS_MAX);
        comp.y = ((comp.y - min_y) * scale).min(CANVAS_MAX);
    }

    vec![DrcError::new(
        T2_NORMALISE,
        "coordinates normalised to 0–300 canvas",
        DrcLevel::Warning,
    )]
}

/// Run the full Tier 2 pipeline on the circuit:
/// 1. Normalise coordinates.
/// 2. Find and correct collisions (up to 20 iterations per pair).
/// 3. Emit T2-02 warning for each pair that could not be resolved.
/// Returns (mutated_components, warnings).
pub fn run_tier2(
    circuit: &OhmaticCircuitV01,
    bboxes: &BboxConfig,
) -> (Vec<Component>, Vec<DrcError>) {
    let mut components: Vec<Component> = circuit.components.clone();
    let mut warnings: Vec<DrcError> = Vec::new();

    // Step 1: normalise coordinates.
    let mut norm_warnings = normalise_coordinates(&mut components, bboxes);
    warnings.append(&mut norm_warnings);

    // Step 2: find collisions.
    let pairs = find_collisions(&components, bboxes);

    // Step 3: correct each colliding pair (up to 20 iterations per pair inside correct_collision).
    for (i, j) in pairs {
        // Safe split borrow: i < j is guaranteed by find_collisions.
        let (left, right) = components.split_at_mut(j);
        correct_collision(&mut left[i], &mut right[0], bboxes);
    }

    // Step 4: re-scan for any remaining collisions after all corrections.
    // Correction of one pair can re-introduce overlap with a third component, so
    // a final pass is needed to emit T2-02 warnings accurately.
    for (i, j) in find_collisions(&components, bboxes) {
        warnings.push(DrcError::new(
            T2_COLLISION,
            format!(
                "unresolvable collision between {} and {}",
                components[i].id, components[j].id
            ),
            DrcLevel::Warning,
        ));
    }

    (components, warnings)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::drc::spatial_hash::aabbs_overlap;
    use crate::drc::spatial_hash::component_aabb;
    use crate::drc::spatial_hash::find_collisions;
    use ohmatic_types::{CircuitMetadata, Component, ComponentType, Net, OhmaticCircuitV01};
    use std::collections::HashMap;
    use std::path::Path;

    fn load_bboxes() -> BboxConfig {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("config/component_registry.toml");
        BboxConfig::load(&path).expect("component_registry.toml must parse")
    }

    fn make_component(id: &str, ct: &str, x: f64, y: f64) -> Component {
        Component {
            id: id.to_string(),
            component_type: ComponentType::new(ct),
            value: "1k".to_string(),
            part: "RES".to_string(),
            x,
            y,
            pins: HashMap::from([("1".to_string(), "a".to_string())]),
        }
    }

    fn minimal_circuit(components: Vec<Component>) -> OhmaticCircuitV01 {
        OhmaticCircuitV01 {
            metadata: CircuitMetadata {
                title: "Test".to_string(),
                description: "Test".to_string(),
                version: "0.1".to_string(),
                tags: vec!["test".to_string()],
            },
            components,
            nets: vec![
                Net {
                    name: "VCC".to_string(),
                    pins: vec!["VCC1.1".to_string(), "R1.1".to_string()],
                },
                Net {
                    name: "GND".to_string(),
                    pins: vec!["GND1.1".to_string(), "R1.1".to_string()],
                },
            ],
        }
    }

    #[test]
    fn normalise_in_range_unchanged() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        let mut comps = vec![
            make_component("R1", "resistor", 10.0, 10.0),
            make_component("R2", "resistor", 50.0, 50.0),
        ];
        let warnings = normalise_coordinates(&mut comps, &bboxes);
        assert!(warnings.is_empty(), "no T2-01 warning expected when coords in range");
        assert_eq!(comps[0].x, 10.0);
        assert_eq!(comps[0].y, 10.0);
        assert_eq!(comps[1].x, 50.0);
        assert_eq!(comps[1].y, 50.0);
    }

    #[test]
    fn normalise_out_of_range() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        let mut comps = vec![
            make_component("R1", "resistor", 0.0, 0.0),
            make_component("R2", "resistor", 500.0, 500.0),
        ];
        let warnings = normalise_coordinates(&mut comps, &bboxes);
        assert_eq!(warnings.len(), 1, "expected exactly one T2-01 warning");
        assert_eq!(warnings[0].rule_id, T2_NORMALISE);
        // After normalisation, all coords must be within [0, CANVAS_MAX].
        for comp in &comps {
            assert!(comp.x >= 0.0 && comp.x <= CANVAS_MAX, "x out of range: {}", comp.x);
            assert!(comp.y >= 0.0 && comp.y <= CANVAS_MAX, "y out of range: {}", comp.y);
        }
    }

    #[test]
    fn run_tier2_identical_coords_corrected() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        let comps = vec![
            make_component("R1", "resistor", 0.0, 0.0),
            make_component("R2", "resistor", 0.0, 0.0),
        ];
        let circuit = minimal_circuit(comps);
        let (result_comps, _warnings) = run_tier2(&circuit, &bboxes);
        assert_eq!(result_comps.len(), 2);
        let aabb_a = component_aabb(&result_comps[0], &bboxes);
        let aabb_b = component_aabb(&result_comps[1], &bboxes);
        assert!(
            !aabbs_overlap(aabb_a, aabb_b),
            "components must not overlap after run_tier2; a={:?}, b={:?}",
            aabb_a,
            aabb_b
        );
    }

    #[test]
    fn run_tier2_no_panic_zero_components() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        let circuit = OhmaticCircuitV01 {
            metadata: CircuitMetadata {
                title: "Empty".to_string(),
                description: "Empty".to_string(),
                version: "0.1".to_string(),
                tags: vec!["test".to_string()],
            },
            components: vec![],
            nets: vec![],
        };
        let (comps, warnings) = run_tier2(&circuit, &bboxes);
        assert!(comps.is_empty());
        assert!(warnings.is_empty());
    }

    /// Verify that run_tier2 does not panic on any seed circuit, and that any
    /// unresolvable collision is represented by a T2-02 warning in the output.
    /// (The spec requires 200 always; unresolvable pairs become warnings, not errors.)
    #[test]
    fn seed_circuits_run_tier2_no_panic_and_t2_warnings_for_unresolvable() {
        let _ = tracing_subscriber::fmt::try_init();
        use serde_json::Value;

        let bboxes = load_bboxes();
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let examples_path =
            std::path::Path::new(manifest_dir).join("../dataset/examples.json");

        let raw = std::fs::read_to_string(&examples_path).unwrap_or_else(|e| {
            panic!("Failed to read {}: {}", examples_path.display(), e)
        });

        let values: Vec<Value> =
            serde_json::from_str(&raw).expect("examples.json must be valid JSON array");

        assert!(!values.is_empty(), "examples.json must not be empty");

        for (idx, val) in values.iter().enumerate() {
            let circuit: OhmaticCircuitV01 = serde_json::from_value(val.clone())
                .unwrap_or_else(|e| panic!("Circuit #{} failed to deserialise: {}", idx, e));

            // Must not panic. Unresolvable collisions are accepted — they become T2-02 warnings.
            let (comps, warnings) = run_tier2(&circuit, &bboxes);

            // Any remaining collision must have a corresponding T2-02 warning in the output.
            let remaining = find_collisions(&comps, &bboxes);
            let t2_02_count = warnings.iter().filter(|w| w.rule_id == T2_COLLISION).count();
            assert!(
                remaining.len() <= t2_02_count,
                "Circuit #{} ('{}') has {} unresolvable collision(s) but only {} T2-02 warning(s)",
                idx,
                circuit.metadata.title,
                remaining.len(),
                t2_02_count
            );
        }
    }

    /// Verify that after normalise_coordinates all component coordinates are within [0, CANVAS_MAX].
    /// Normalisation does not guarantee zero collisions — components may share coordinates.
    #[test]
    fn seed_circuits_post_normalise_coords_in_range() {
        let _ = tracing_subscriber::fmt::try_init();
        use serde_json::Value;

        let bboxes = load_bboxes();
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let examples_path =
            std::path::Path::new(manifest_dir).join("../dataset/examples.json");

        let raw = std::fs::read_to_string(&examples_path).unwrap_or_else(|e| {
            panic!("Failed to read {}: {}", examples_path.display(), e)
        });

        let values: Vec<Value> =
            serde_json::from_str(&raw).expect("examples.json must be valid JSON array");

        assert!(!values.is_empty(), "examples.json must not be empty");

        for (idx, val) in values.iter().enumerate() {
            let circuit: OhmaticCircuitV01 = serde_json::from_value(val.clone())
                .unwrap_or_else(|e| panic!("Circuit #{} failed to deserialise: {}", idx, e));

            let mut components = circuit.components.clone();
            normalise_coordinates(&mut components, &bboxes);

            for comp in &components {
                assert!(
                    comp.x >= 0.0 && comp.x <= CANVAS_MAX,
                    "Circuit #{} ('{}') component {} x={} out of [0,{}] after normalise",
                    idx, circuit.metadata.title, comp.id, comp.x, CANVAS_MAX
                );
                assert!(
                    comp.y >= 0.0 && comp.y <= CANVAS_MAX,
                    "Circuit #{} ('{}') component {} y={} out of [0,{}] after normalise",
                    idx, circuit.metadata.title, comp.id, comp.y, CANVAS_MAX
                );
            }
        }
    }
}
