// Tier 3 electrical correctness rules (T3-01 through T3-08).
// Called by the verifier HTTP handler after Tier 1 and Tier 2 pass.
//
// Stage 1 scope limitations:
// - Single VCC domain assumed. Circuits with multiple supply rails (VCC_3V3, VCC_5V, VEE)
//   are flagged with T3-INFO-01, but only the net literally named "VCC" is inspected by
//   rules T3-04 and T3-06. Full multi-rail analysis is deferred to Stage 3.
// - Differential pairs, transmission lines, and impedance matching are out of scope.
// - Thermal analysis and power dissipation checks are out of scope.
// - Rule T3-03 (floating gate) uses a structural net heuristic — false negatives are
//   possible when gate bias is supplied by a component not in GATE_DRIVER_TYPES.

use std::collections::{HashMap, HashSet};
use ohmatic_types::{component_types as ct, OhmaticCircuitV01};
use crate::drc::rule_ids::T3_MULTI_RAIL;
use crate::drc::schema_rules::{DrcError, DrcLevel};

// Component types that count as a valid gate driver or bias source for T3-03.
// A MOSFET gate net that contains at least one of these does not trigger the floating-gate violation.
const GATE_DRIVER_TYPES: &[&str] = &[
    ct::RESISTOR, ct::POWER_VCC, ct::POWER_GND,
    ct::IC_DRIVER, ct::IC_LOGIC, ct::IC_MCU,
    ct::CONNECTOR,
];

// IC types that must have at least one pin on the "VCC" net (T3-06).
// Types that commonly operate from a split or negative supply (e.g. ic_opamp in bipolar mode)
// are still included because the Stage 1 single-VCC assumption requires a VCC connection.
const IC_TYPES_WITH_VCC: &[&str] = &[
    ct::IC_OPAMP, ct::IC_TIMER, ct::IC_REGULATOR,
    ct::IC_LOGIC, ct::IC_MCU, ct::IC_DRIVER,
];

// Component types exempt from the T3-07 BFS isolation check.
// These components are legitimately the outermost nodes of a circuit (connectors, power symbols,
// mechanical/electromechanical parts) and need not be reachable from a power net to be valid.
const T3_07_EXEMPT: &[&str] = &[
    ct::POWER_VCC, ct::POWER_GND, ct::CONNECTOR,
    ct::BUTTON, ct::CRYSTAL, ct::SPEAKER,
    ct::SENSOR, ct::INDUCTOR,
];

pub fn run_tier3(circuit: &OhmaticCircuitV01) -> Vec<DrcError> {
    let mut warnings: Vec<DrcError> = Vec::new();

    // --- index: net name → set of component IDs on that net ---
    let mut net_to_comps: HashMap<&str, HashSet<&str>> = HashMap::new();
    for net in &circuit.nets {
        for pin_ref in &net.pins {
            if let Some((comp_id, _)) = pin_ref.split_once('.') {
                net_to_comps.entry(net.name.as_str()).or_default().insert(comp_id);
            }
        }
    }

    // T3-INFO-01: multi-rail circuit detected.
    // Stage 1 only inspects the net literally named "VCC". Circuits that carry
    // multiple independent supply rails (e.g. power_3v3 + power_5v + power_vcc)
    // will only be partially checked — emit an INFO marker so the caller knows.
    const NAMED_RAIL_TYPES: &[&str] = &[
        ct::POWER_VCC, ct::POWER_VEE, ct::POWER_3V3, ct::POWER_5V, ct::POWER_12V,
    ];
    let rail_types_present: HashSet<&str> = circuit.components.iter()
        .map(|c| c.component_type.as_str())
        .filter(|t| NAMED_RAIL_TYPES.contains(t))
        .collect();
    if rail_types_present.len() > 1 {
        let rail_list: Vec<&str> = {
            let mut v: Vec<&str> = rail_types_present.into_iter().collect();
            v.sort_unstable();
            v
        };
        warnings.push(DrcError::new(
            T3_MULTI_RAIL,
            format!(
                "multi-rail circuit: {} — Stage 1 only inspects net 'VCC'; \
                 full multi-rail analysis deferred to Stage 3",
                rail_list.join(", ")
            ),
            DrcLevel::Info,
        ));
    }

    // T3-01: short circuit — net with both PowerVcc and PowerGnd pin
    for net in &circuit.nets {
        let comps_on = net_to_comps.get(net.name.as_str()).cloned().unwrap_or_default();
        let has_vcc = circuit.components.iter()
            .any(|c| c.component_type.as_str() == ct::POWER_VCC && comps_on.contains(c.id.as_str()));
        let has_gnd = circuit.components.iter()
            .any(|c| c.component_type.as_str() == ct::POWER_GND && comps_on.contains(c.id.as_str()));
        if has_vcc && has_gnd {
            warnings.push(DrcError::new("T3-01",
                format!("short circuit: net '{}' connects VCC and GND directly", net.name),
                DrcLevel::Violation));
        }
    }

    // T3-02: LED without current limiting resistor on anode net.
    // Exception: if a transistor (NPN/PNP) or MOSFET (N/P) has a pin on the anode net,
    // that active device is acting as the current controller — rule does not fire.
    for comp in circuit.components.iter().filter(|c| c.component_type.as_str() == ct::LED) {
        if !comp.pins.contains_key("A") { continue; }
        let anode_ref = format!("{}.A", comp.id);
        let anode_net = circuit.nets.iter().find(|n| n.pins.contains(&anode_ref));
        if let Some(net) = anode_net {
            let has_resistor = circuit.components.iter()
                .filter(|c| c.component_type.as_str() == ct::RESISTOR)
                .any(|r| net.pins.iter().any(|p| p.starts_with(&format!("{}.", r.id))));
            if has_resistor { continue; }

            // Active device on anode net acts as current limiter — exempt.
            let active_device_types: &[&str] = &[
                ct::TRANSISTOR_NPN, ct::TRANSISTOR_PNP, ct::MOSFET_N, ct::MOSFET_P,
            ];
            let has_active_device = circuit.components.iter()
                .any(|c| active_device_types.contains(&c.component_type.as_str())
                    && net.pins.iter().any(|p| p.starts_with(&format!("{}.", c.id))));
            if has_active_device { continue; }

            warnings.push(DrcError::new("T3-02",
                format!("{}: LED anode net '{}' has no current-limiting resistor", comp.id, net.name),
                DrcLevel::Violation));
        }
    }

    // T3-03: floating MOSFET gate
    for comp in circuit.components.iter()
        .filter(|c| matches!(c.component_type.as_str(), ct::MOSFET_N | ct::MOSFET_P))
    {
        if !comp.pins.contains_key("G") { continue; }
        let gate_ref = format!("{}.G", comp.id);
        let gate_net = circuit.nets.iter().find(|n| n.pins.contains(&gate_ref));
        if let Some(net) = gate_net {
            let has_driver = circuit.components.iter()
                .filter(|c| c.id != comp.id)
                .any(|c| GATE_DRIVER_TYPES.contains(&c.component_type.as_str())
                     && net.pins.iter().any(|p| p.starts_with(&format!("{}.", c.id))));
            if !has_driver {
                warnings.push(DrcError::new("T3-03",
                    format!("{}: MOSFET gate on net '{}' has no driver or bias component", comp.id, net.name),
                    DrcLevel::Violation));
            }
        }
    }

    // T3-04: missing bypass capacitor on VCC net (per IC instance)
    if let Some(vcc_net) = circuit.nets.iter().find(|n| n.name == "VCC") {
        let cap_on_vcc = circuit.components.iter()
            .filter(|c| c.component_type.as_str() == ct::CAPACITOR)
            .any(|c| vcc_net.pins.iter().any(|p| p.starts_with(&format!("{}.", c.id))));

        for comp in circuit.components.iter()
            .filter(|c| matches!(c.component_type.as_str(), ct::IC_MCU | ct::IC_OPAMP))
        {
            let ic_on_vcc = vcc_net.pins.iter().any(|p| p.starts_with(&format!("{}.", comp.id)));
            if ic_on_vcc && !cap_on_vcc {
                warnings.push(DrcError::new("T3-04",
                    format!("{}: IC has no bypass capacitor on VCC net", comp.id),
                    DrcLevel::Warning));
            }
        }
    }

    // T3-05: reverse-polarity capacitor
    // Fires ONLY when positive pin→GND net or negative pin→VCC net (literal names)
    for comp in circuit.components.iter()
        .filter(|c| c.component_type.as_str() == ct::CAPACITOR)
    {
        for pos_pin in &["1", "+"] {
            if comp.pins.contains_key(*pos_pin) {
                let pin_ref = format!("{}.{}", comp.id, pos_pin);
                let on_gnd = circuit.nets.iter()
                    .any(|n| n.name == "GND" && n.pins.contains(&pin_ref));
                if on_gnd {
                    warnings.push(DrcError::new("T3-05",
                        format!("{}: capacitor positive pin '{}' connected to GND", comp.id, pos_pin),
                        DrcLevel::Violation));
                }
            }
        }
        for neg_pin in &["2", "-"] {
            if comp.pins.contains_key(*neg_pin) {
                let pin_ref = format!("{}.{}", comp.id, neg_pin);
                let on_vcc = circuit.nets.iter()
                    .any(|n| n.name == "VCC" && n.pins.contains(&pin_ref));
                if on_vcc {
                    warnings.push(DrcError::new("T3-05",
                        format!("{}: capacitor negative pin '{}' connected to VCC", comp.id, neg_pin),
                        DrcLevel::Violation));
                }
            }
        }
    }

    // T3-06: IC with no pin on VCC net
    let vcc_pins: HashSet<&str> = circuit.nets.iter()
        .find(|n| n.name == "VCC")
        .map(|n| n.pins.iter().map(String::as_str).collect())
        .unwrap_or_default();

    for comp in circuit.components.iter()
        .filter(|c| IC_TYPES_WITH_VCC.contains(&c.component_type.as_str()))
    {
        let prefix = format!("{}.", comp.id);
        let on_vcc = vcc_pins.iter().any(|p| p.starts_with(&prefix));
        if !on_vcc {
            warnings.push(DrcError::new("T3-06",
                format!("{}: IC has no pin connected to VCC net", comp.id),
                DrcLevel::Warning));
        }
    }

    // T3-07: isolated component (BFS from power nets)
    let mut adj: HashMap<&str, HashSet<&str>> = HashMap::new();
    for net in &circuit.nets {
        let ids: Vec<&str> = net.pins.iter()
            .filter_map(|p| p.split_once('.').map(|(id, _)| id))
            .collect();
        for &a in &ids {
            for &b in &ids {
                if a != b { adj.entry(a).or_default().insert(b); }
            }
        }
    }
    let mut reachable: HashSet<&str> = HashSet::new();
    let mut queue: std::collections::VecDeque<&str> = std::collections::VecDeque::new();
    for comp in circuit.components.iter()
        .filter(|c| matches!(c.component_type.as_str(), ct::POWER_VCC | ct::POWER_GND))
    {
        if reachable.insert(comp.id.as_str()) { queue.push_back(comp.id.as_str()); }
    }
    while let Some(id) = queue.pop_front() {
        for &nb in adj.get(id).into_iter().flatten() {
            if reachable.insert(nb) { queue.push_back(nb); }
        }
    }
    for comp in &circuit.components {
        if T3_07_EXEMPT.contains(&comp.component_type.as_str()) { continue; }
        if !reachable.contains(comp.id.as_str()) {
            warnings.push(DrcError::new("T3-07",
                format!("{}: component is not reachable from any power net", comp.id),
                DrcLevel::Warning));
        }
    }

    // T3-08: button with no pull-up/pull-down resistor
    for comp in circuit.components.iter()
        .filter(|c| c.component_type.as_str() == ct::BUTTON)
    {
        let pin1_ref = format!("{}.1", comp.id);
        let output_net = circuit.nets.iter()
            .find(|n| n.pins.contains(&pin1_ref))
            .or_else(|| circuit.nets.iter().find(|n|
                n.name != "VCC" && n.name != "GND"
                && n.pins.iter().any(|p| p.starts_with(&format!("{}.", comp.id)))));
        if let Some(net) = output_net {
            let has_res = circuit.components.iter()
                .filter(|c| c.component_type.as_str() == ct::RESISTOR)
                .any(|r| net.pins.iter().any(|p| p.starts_with(&format!("{}.", r.id))));
            if !has_res {
                warnings.push(DrcError::new("T3-08",
                    format!("{}: button has no pull-up/pull-down resistor on net '{}'", comp.id, net.name),
                    DrcLevel::Warning));
            }
        }
    }

    warnings
}

#[cfg(test)]
mod tests {
    use super::*;
    use ohmatic_types::{CircuitMetadata, Component, ComponentType, Net, OhmaticCircuitV01};


    fn meta() -> CircuitMetadata {
        CircuitMetadata {
            title: "T".to_string(), description: "D".to_string(),
            version: "0.1".to_string(), tags: vec!["t".to_string()],
        }
    }

    /// Build a Component. `ct` is a snake_case component type string (e.g. "resistor").
    fn comp(id: &str, ct: &str, pins: Vec<(&str, &str)>) -> Component {
        Component {
            id: id.to_string(), component_type: ComponentType::new(ct),
            value: "".to_string(), part: "".to_string(), x: 0.0, y: 0.0,
            pins: pins.into_iter().map(|(k,v)| (k.to_string(), v.to_string())).collect(),
        }
    }

    fn net(name: &str, pins: &[&str]) -> Net {
        Net { name: name.to_string(), pins: pins.iter().map(|s| s.to_string()).collect() }
    }

    fn circuit(components: Vec<Component>, nets: Vec<Net>) -> OhmaticCircuitV01 {
        OhmaticCircuitV01 { metadata: meta(), components, nets }
    }

    // --- T3-01 ---

    #[test]
    fn t3_01_pass() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("R1",   ct::RESISTOR,  vec![("1","v"),("2","g")])],
            vec![net("VCC",&["VCC1.1","R1.1"]), net("GND",&["GND1.1","R1.2"])],
        );
        assert!(!run_tier3(&c).iter().any(|e| e.rule_id == "T3-01"));
    }

    #[test]
    fn t3_01_violation() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","s")]),
                 comp("GND1", ct::POWER_GND, vec![("1","s")]),
                 comp("R1",   ct::RESISTOR,  vec![("1","s"),("2","s")])],
            vec![net("SHORT",&["VCC1.1","GND1.1","R1.1","R1.2"])],
        );
        assert!(run_tier3(&c).iter().any(|e| e.rule_id == "T3-01"));
    }

    // --- T3-02 ---

    #[test]
    fn t3_02_pass() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("R1",   ct::RESISTOR,  vec![("1","v"),("2","m")]),
                 comp("LED1", ct::LED,        vec![("A","m"),("K","g")])],
            vec![net("VCC",&["VCC1.1","R1.1"]),
                 net("MID",&["R1.2","LED1.A"]),
                 net("GND",&["GND1.1","LED1.K"])],
        );
        assert!(!run_tier3(&c).iter().any(|e| e.rule_id == "T3-02"));
    }

    #[test]
    fn t3_02_violation() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("LED1", ct::LED,        vec![("A","v"),("K","g")])],
            vec![net("VCC",&["VCC1.1","LED1.A"]), net("GND",&["GND1.1","LED1.K"])],
        );
        assert!(run_tier3(&c).iter().any(|e| e.rule_id == "T3-02"));
    }

    // --- T3-03 ---

    #[test]
    fn t3_03_pass() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("R1",   ct::RESISTOR,  vec![("1","v"),("2","gate_net")]),
                 comp("Q1",   ct::MOSFET_N,  vec![("G","gate_net"),("D","v"),("S","g")])],
            vec![net("VCC",&["VCC1.1","R1.1","Q1.D"]),
                 net("GATE",&["R1.2","Q1.G"]),
                 net("GND",&["GND1.1","Q1.S"])],
        );
        assert!(!run_tier3(&c).iter().any(|e| e.rule_id == "T3-03"));
    }

    #[test]
    fn t3_03_violation() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("Q1",   ct::MOSFET_N,  vec![("G","gn"),("D","v"),("S","g")]),
                 comp("Q2",   ct::MOSFET_N,  vec![("G","gn"),("D","v"),("S","g")])],
            vec![net("VCC",&["VCC1.1","Q1.D","Q2.D"]),
                 net("GND",&["GND1.1","Q1.S","Q2.S"]),
                 net("GATE",&["Q1.G","Q2.G"])],
        );
        assert!(run_tier3(&c).iter().any(|e| e.rule_id == "T3-03"));
    }

    // --- T3-04 ---

    #[test]
    fn t3_04_pass() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("U1",   ct::IC_OPAMP,   vec![("VCC","v"),("GND","g"),("OUT","g")]),
                 comp("C1",   ct::CAPACITOR,  vec![("1","v"),("2","g")])],
            vec![net("VCC",&["VCC1.1","U1.VCC","C1.1"]),
                 net("GND",&["GND1.1","U1.GND","U1.OUT","C1.2"])],
        );
        assert!(!run_tier3(&c).iter().any(|e| e.rule_id == "T3-04"));
    }

    #[test]
    fn t3_04_violation() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("U1",   ct::IC_OPAMP,   vec![("VCC","v"),("GND","g"),("OUT","g")])],
            vec![net("VCC",&["VCC1.1","U1.VCC"]),
                 net("GND",&["GND1.1","U1.GND","U1.OUT"])],
        );
        assert!(run_tier3(&c).iter().any(|e| e.rule_id == "T3-04"));
    }

    // --- T3-05 ---

    #[test]
    fn t3_05_pass() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("C1",   ct::CAPACITOR,  vec![("1","v"),("2","g")])],
            vec![net("VCC",&["VCC1.1","C1.1"]), net("GND",&["GND1.1","C1.2"])],
        );
        assert!(!run_tier3(&c).iter().any(|e| e.rule_id == "T3-05"));
    }

    #[test]
    fn t3_05_violation() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("C1",   ct::CAPACITOR,  vec![("1","g"),("2","v")])],
            vec![net("VCC",&["VCC1.1","C1.2"]), net("GND",&["GND1.1","C1.1"])],
        );
        assert!(run_tier3(&c).iter().any(|e| e.rule_id == "T3-05"));
    }

    // --- T3-06 ---

    #[test]
    fn t3_06_pass() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("U1",   ct::IC_TIMER,   vec![("VCC","v"),("GND","g"),("OUT","g")])],
            vec![net("VCC",&["VCC1.1","U1.VCC"]), net("GND",&["GND1.1","U1.GND","U1.OUT"])],
        );
        assert!(!run_tier3(&c).iter().any(|e| e.rule_id == "T3-06"));
    }

    #[test]
    fn t3_06_violation() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("U1",   ct::IC_TIMER,   vec![("GND","g"),("OUT","g")])],
            vec![net("VCC",&["VCC1.1"]), net("GND",&["GND1.1","U1.GND","U1.OUT"])],
        );
        assert!(run_tier3(&c).iter().any(|e| e.rule_id == "T3-06"));
    }

    // --- T3-07 ---

    #[test]
    fn t3_07_pass() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("R1",   ct::RESISTOR,  vec![("1","v"),("2","g")])],
            vec![net("VCC",&["VCC1.1","R1.1"]), net("GND",&["GND1.1","R1.2"])],
        );
        assert!(!run_tier3(&c).iter().any(|e| e.rule_id == "T3-07"));
    }

    #[test]
    fn t3_07_violation() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("R1",   ct::RESISTOR,  vec![("1","v"),("2","g")]),
                 comp("R2",   ct::RESISTOR,  vec![("1","x"),("2","y")])],
            vec![net("VCC",&["VCC1.1","R1.1"]),
                 net("GND",&["GND1.1","R1.2"]),
                 net("ISLAND_A",&["R2.1"]),
                 net("ISLAND_B",&["R2.2"])],
        );
        assert!(run_tier3(&c).iter().any(|e| e.rule_id == "T3-07"));
    }

    // --- T3-08 ---

    #[test]
    fn t3_08_pass() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("R1",   ct::RESISTOR,  vec![("1","v"),("2","sig")]),
                 comp("SW1",  ct::BUTTON,    vec![("1","sig"),("2","g")])],
            vec![net("VCC",&["VCC1.1","R1.1"]),
                 net("SIG",&["R1.2","SW1.1"]),
                 net("GND",&["GND1.1","SW1.2"])],
        );
        assert!(!run_tier3(&c).iter().any(|e| e.rule_id == "T3-08"));
    }

    #[test]
    fn t3_08_violation() {
        let _ = tracing_subscriber::fmt::try_init();
        let c = circuit(
            vec![comp("VCC1", ct::POWER_VCC, vec![("1","v")]),
                 comp("GND1", ct::POWER_GND, vec![("1","g")]),
                 comp("SW1",  ct::BUTTON,    vec![("1","sig"),("2","g")])],
            vec![net("VCC",&["VCC1.1"]),
                 net("SIG",&["SW1.1"]),
                 net("GND",&["GND1.1","SW1.2"])],
        );
        assert!(run_tier3(&c).iter().any(|e| e.rule_id == "T3-08"));
    }

    // --- Seed circuits — no Violation-level findings ---

    #[test]
    fn seed_circuits_no_violations() {
        let _ = tracing_subscriber::fmt::try_init();
        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let path = std::path::Path::new(manifest_dir).join("../dataset/examples.json");
        let raw = std::fs::read_to_string(&path).expect("examples.json must exist");
        let values: Vec<serde_json::Value> = serde_json::from_str(&raw).unwrap();
        for (idx, v) in values.iter().enumerate() {
            let circuit: OhmaticCircuitV01 = serde_json::from_value(v.clone())
                .unwrap_or_else(|e| panic!("circuit {} failed to deserialise: {}", idx, e));
            let findings = run_tier3(&circuit);
            let violations: Vec<_> = findings.iter()
                .filter(|f| f.level == DrcLevel::Violation)
                .collect();
            assert!(violations.is_empty(),
                "circuit {} '{}' has Violation-level T3 findings: {:?}",
                idx, circuit.metadata.title,
                violations.iter().map(|f| f.to_wire()).collect::<Vec<_>>());
        }
    }
} // end mod tests
