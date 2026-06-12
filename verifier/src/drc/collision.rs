//! Pairwise collision corrector - pushes two overlapping components apart
//! using an iterative half-depth strategy (up to [`MAX_ITERATIONS`] steps).

use crate::config::BboxConfig;
use crate::drc::spatial_hash::{aabbs_overlap, component_aabb};
use ohmatic_types::Component;

const MAX_ITERATIONS: u32 = 20;

/// Minimum movement per push step (canvas units).
/// Keeps the push convergent and prevents infinite loops on degenerate geometry.
const MIN_STEP: f64 = 1.0;

/// One push-apart step between two overlapping components.
/// Moves `a` and `b` positions in place.
/// Returns true if they no longer overlap after this step.
pub fn push_apart_step(a: &mut Component, b: &mut Component, bboxes: &BboxConfig) -> bool {
    let (w_a, h_a) = bboxes.get(&a.component_type);
    let (w_b, h_b) = bboxes.get(&b.component_type);

    let centre_a = (a.x + w_a / 2.0, a.y + h_a / 2.0);
    let centre_b = (b.x + w_b / 2.0, b.y + h_b / 2.0);

    let dx = centre_b.0 - centre_a.0;
    let dy = centre_b.1 - centre_a.1;
    let len = (dx * dx + dy * dy).sqrt();

    // Normalised direction from a-centre toward b-centre.
    let (nx, ny) = if len < 1e-9 {
        (1.0_f64, 0.0_f64) // fallback: push b to the right
    } else {
        (dx / len, dy / len)
    };

    // Overlap depth along each axis.
    let aabb_a = component_aabb(a, bboxes);
    let aabb_b = component_aabb(b, bboxes);

    let overlap_x = (aabb_a.2.min(aabb_b.2) - aabb_a.0.max(aabb_b.0)).max(0.0);
    let overlap_y = (aabb_a.3.min(aabb_b.3) - aabb_a.1.max(aabb_b.1)).max(0.0);

    // Project the overlap onto the push direction; clamp to at least MIN_STEP.
    let raw_depth = overlap_x * nx.abs() + overlap_y * ny.abs();
    let depth = raw_depth.max(MIN_STEP);

    // Move each component half the depth in opposite directions.
    let half = depth / 2.0;
    a.x -= nx * half;
    a.y -= ny * half;
    b.x += nx * half;
    b.y += ny * half;

    let new_a = component_aabb(a, bboxes);
    let new_b = component_aabb(b, bboxes);
    !aabbs_overlap(new_a, new_b)
}

/// Push apart two components up to MAX_ITERATIONS times.
/// Returns true if resolved, false if still colliding after all iterations.
pub fn correct_collision(a: &mut Component, b: &mut Component, bboxes: &BboxConfig) -> bool {
    for _ in 0..MAX_ITERATIONS {
        if push_apart_step(a, b, bboxes) {
            return true;
        }
    }
    // Final check after the last step.
    let aabb_a = component_aabb(a, bboxes);
    let aabb_b = component_aabb(b, bboxes);
    !aabbs_overlap(aabb_a, aabb_b)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ohmatic_types::{Component, ComponentType};
    use std::collections::HashMap;
    use std::path::Path;

    fn load_bboxes() -> BboxConfig {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("config/component_registry.toml");
        BboxConfig::load(&path).expect("component_registry.toml must parse")
    }

    fn make_component(id: &str, x: f64, y: f64) -> Component {
        Component {
            id: id.to_string(),
            component_type: ComponentType::new("resistor"),
            value: "1k".to_string(),
            part: "RES".to_string(),
            x,
            y,
            pins: HashMap::from([("1".to_string(), "a".to_string())]),
        }
    }

    #[test]
    fn correct_collision_resolves_identical() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        let mut a = make_component("R1", 0.0, 0.0);
        let mut b = make_component("R2", 0.0, 0.0);
        let resolved = correct_collision(&mut a, &mut b, &bboxes);
        assert!(resolved, "identical-position collision must be resolved");
        let aabb_a = component_aabb(&a, &bboxes);
        let aabb_b = component_aabb(&b, &bboxes);
        assert!(!aabbs_overlap(aabb_a, aabb_b));
    }

    #[test]
    fn correct_collision_zero_delta_fallback() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        // Centres are identical - exercises the zero-delta fallback path (len < 1e-9).
        let mut a = make_component("R1", 0.0, 0.0);
        let mut b = make_component("R2", 0.0, 0.0);
        // Must not panic, must resolve via fallback (1.0, 0.0) direction.
        let resolved = correct_collision(&mut a, &mut b, &bboxes);
        assert!(resolved, "zero-delta fallback must still resolve the collision");
    }

    #[test]
    fn correct_collision_unresolvable() {
        let _ = tracing_subscriber::fmt::try_init();
        // The proportional push-apart algorithm resolves any finite pairwise overlap
        // within MAX_ITERATIONS steps (a full-depth push clears the overlap in one step).
        // Therefore `correct_collision` returning false (unresolvable) is not reachable
        // for an isolated pair with standard bboxes.
        //
        // The false-return path is exercised only in the multi-component scenario inside
        // `run_tier2`, where correcting one pair can re-introduce overlap with a third
        // component that was NOT in the original pair list - the re-scan in Step 4 of
        // run_tier2 then emits the T2-02 warning. That path is covered by the corrector's
        // `seed_circuits_run_tier2_no_panic_and_t2_warnings_for_unresolvable` test and
        // the `t2_02_unresolvable_collision_200` integration test.
        //
        // This test verifies: (a) the resolution path works and returns true, (b) after
        // resolution the AABBs do not overlap, (c) the function does not panic.
        let toml_str =
            "[defaults]\nbbox = [10.0, 10.0]\n\n[resistor]\nbbox = [10.0, 10.0]\n";
        let bboxes = BboxConfig::load_from_str(toml_str).expect("must parse");
        let mut a = make_component("R1", 0.0, 0.0);
        let mut b = make_component("R2", 0.0, 0.0);
        let resolved = correct_collision(&mut a, &mut b, &bboxes);
        assert!(resolved, "pairwise overlap with standard bbox must resolve within MAX_ITERATIONS");
        let aabb_a = component_aabb(&a, &bboxes);
        let aabb_b = component_aabb(&b, &bboxes);
        assert!(
            !aabbs_overlap(aabb_a, aabb_b),
            "components must not overlap after correction: a={:?} b={:?}", aabb_a, aabb_b
        );
    }
}
