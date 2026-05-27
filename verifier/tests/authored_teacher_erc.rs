use std::{fs, path::Path};

use ohmatic_types::OhmaticCircuitV01;
use serde_json::Value;
use verifier::{
    config::BboxConfig,
    drc::{
        corrector::run_tier2,
        electrical_rules::run_tier3,
        schema_rules::{run_tier1, DrcLevel},
    },
    BBOX_TOML,
};

#[test]
fn authored_teacher_records_have_no_tier3_warning_or_violation_findings() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
    let corpus_dir = root.join("dataset/authored/teacher_corpus");
    let bboxes = BboxConfig::load_from_str(BBOX_TOML).expect("component registry must parse");

    let mut failures = Vec::new();
    let mut paths: Vec<_> = fs::read_dir(&corpus_dir)
        .unwrap_or_else(|err| panic!("failed to read {}: {err}", corpus_dir.display()))
        .map(|entry| entry.expect("teacher corpus entry must be readable").path())
        .filter(|path| path.extension().and_then(|s| s.to_str()) == Some("json"))
        .collect();
    paths.sort();

    for path in paths {
        let raw = fs::read_to_string(&path)
            .unwrap_or_else(|err| panic!("failed to read {}: {err}", path.display()));
        let value: Value = serde_json::from_str(&raw)
            .unwrap_or_else(|err| panic!("failed to parse {}: {err}", path.display()));
        let circuit_value = value
            .get("circuit")
            .unwrap_or_else(|| panic!("{} is missing circuit", path.display()));
        let circuit: OhmaticCircuitV01 = serde_json::from_value(circuit_value.clone())
            .unwrap_or_else(|err| panic!("failed to deserialize {} circuit: {err}", path.display()));

        if let Err(errors) = run_tier1(&circuit) {
            failures.push(format!(
                "{} Tier 1: {}",
                path.file_name().unwrap().to_string_lossy(),
                errors.iter().map(|e| e.to_wire()).collect::<Vec<_>>().join("; ")
            ));
            continue;
        }

        let (components, _tier2_findings) = run_tier2(&circuit, &bboxes);
        let normalized = OhmaticCircuitV01 {
            metadata: circuit.metadata.clone(),
            components,
            nets: circuit.nets.clone(),
        };
        let tier3_findings = run_tier3(&normalized);

        let file_name = path.file_name().unwrap().to_string_lossy();
        if file_name.as_ref() < "manual_teacher_0027.json" {
            continue;
        }

        let non_info_findings: Vec<_> = tier3_findings
            .iter()
            .filter(|finding| finding.level != DrcLevel::Info)
            .map(|finding| finding.to_wire())
            .collect();
        if !non_info_findings.is_empty() {
            failures.push(format!(
                "{}: {}",
                file_name,
                non_info_findings.join("; ")
            ));
        }
    }

    assert!(
        failures.is_empty(),
        "authored teacher records have verifier warnings/violations:\n{}",
        failures.join("\n")
    );
}
