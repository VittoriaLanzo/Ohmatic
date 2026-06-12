//! DRC module - Tier 1 (schema rules), Tier 2 (geometry correction), Tier 3 (electrical rules).

pub mod rule_ids;
pub mod schema_rules;
pub mod spatial_hash;
pub mod collision;
pub mod corrector;
pub mod electrical_rules;
