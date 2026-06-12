//! Central rule-ID constants - prevents typos across modules.
//! Add a constant here whenever a new rule ID is introduced; use the constant
//! everywhere instead of a bare string literal.

/// Tier 2: component position normalised to the 0-300 viewport grid.
pub const T2_NORMALISE: &str = "T2-01";

/// Tier 2: axis-aligned bounding-box collision between two components.
pub const T2_COLLISION: &str = "T2-02";

/// Tier 1: a pin reference appears in more than one net (electrical short).
/// Distinct from T1-07 (unknown component/pin) to allow gateway and monitoring
/// to distinguish "shorted pin" from "missing component" without string-matching.
pub const T1_SHORT: &str = "T1-SHORT";

/// Informational: circuit contains more than one distinct power-rail type.
/// Stage 1 inspects only the net named "VCC". Multi-rail correctness is Stage 3.
pub const T3_MULTI_RAIL: &str = "T3-INFO-01";
