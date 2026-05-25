//! Spatial hash grid for broad-phase AABB collision detection.
//! Maps each component's bounding box into a uniform grid and returns
//! all (i, j) index pairs whose AABBs overlap (each pair reported once).

use std::collections::{HashMap, HashSet};

use crate::config::BboxConfig;
use ohmatic_types::Component;

/// Grid cell size for the spatial hash (in canvas units).
const CELL_SIZE: f64 = 20.0;

/// Compute the AABB for a single component: (min_x, min_y, max_x, max_y).
pub fn component_aabb(c: &Component, bboxes: &BboxConfig) -> (f64, f64, f64, f64) {
    let (w, h) = bboxes.get(&c.component_type);
    (c.x, c.y, c.x + w, c.y + h)
}

/// Returns true iff two AABBs overlap (touching edges count as overlap).
pub fn aabbs_overlap(a: (f64, f64, f64, f64), b: (f64, f64, f64, f64)) -> bool {
    !(a.2 <= b.0 || b.2 <= a.0 || a.3 <= b.1 || b.3 <= a.1)
}

/// Returns a list of (i, j) index pairs of components whose bounding boxes overlap.
/// Each pair appears exactly once: i < j.
pub fn find_collisions(components: &[Component], bboxes: &BboxConfig) -> Vec<(usize, usize)> {
    if components.len() < 2 {
        return vec![];
    }

    // Map each component into every grid cell its AABB touches.
    let mut grid: HashMap<(i64, i64), Vec<usize>> = HashMap::new();
    for (idx, comp) in components.iter().enumerate() {
        let (min_x, min_y, max_x, max_y) = component_aabb(comp, bboxes);
        let cell_min_x = (min_x / CELL_SIZE).floor() as i64;
        let cell_max_x = (max_x / CELL_SIZE).floor() as i64;
        let cell_min_y = (min_y / CELL_SIZE).floor() as i64;
        let cell_max_y = (max_y / CELL_SIZE).floor() as i64;
        for cx in cell_min_x..=cell_max_x {
            for cy in cell_min_y..=cell_max_y {
                grid.entry((cx, cy)).or_default().push(idx);
            }
        }
    }

    // Check every candidate pair inside each bucket; track seen pairs to avoid duplicates.
    let mut seen: HashSet<(usize, usize)> = HashSet::new();
    let mut result: Vec<(usize, usize)> = Vec::new();

    for indices in grid.values() {
        if indices.len() < 2 {
            continue;
        }
        for a in 0..indices.len() {
            for b in (a + 1)..indices.len() {
                let i = indices[a].min(indices[b]);
                let j = indices[a].max(indices[b]);
                if seen.insert((i, j)) {
                    let aabb_i = component_aabb(&components[i], bboxes);
                    let aabb_j = component_aabb(&components[j], bboxes);
                    if aabbs_overlap(aabb_i, aabb_j) {
                        result.push((i, j));
                    }
                }
            }
        }
    }

    result.sort_unstable();
    result
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
    fn no_collision_empty() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        let result = find_collisions(&[], &bboxes);
        assert!(result.is_empty());
    }

    #[test]
    fn no_collision_one() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        let comps = vec![make_component("R1", 0.0, 0.0)];
        let result = find_collisions(&comps, &bboxes);
        assert!(result.is_empty());
    }

    #[test]
    fn collision_identical_coords() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        let comps = vec![
            make_component("R1", 0.0, 0.0),
            make_component("R2", 0.0, 0.0),
        ];
        let result = find_collisions(&comps, &bboxes);
        assert_eq!(result, vec![(0, 1)]);
    }

    #[test]
    fn no_collision_separated() {
        let _ = tracing_subscriber::fmt::try_init();
        let bboxes = load_bboxes();
        // Resistor bbox is 8×4; place them 200 units apart — no overlap.
        let comps = vec![
            make_component("R1", 0.0, 0.0),
            make_component("R2", 200.0, 200.0),
        ];
        let result = find_collisions(&comps, &bboxes);
        assert!(result.is_empty());
    }
}
