#!/usr/bin/env python3
"""Static diagnostic feedback for malformed or risky Ohmatic schematics."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

from dataset import validate
from dataset.teacher_corpus import COMPONENT_CARDS
from eval import diagnostic_rules


REGISTRY_PATH = ROOT / "verifier/config/component_registry.toml"
DEFAULT_TAXONOMY_PATH = ROOT / "eval/error_taxonomy.json"


# ── Component-type normalization ──────────────────────────────────────────────
# The corpus uses a few synonym type names for components that already have a
# canonical registry type with identical electrical treatment. We fold synonyms to
# canonical BEFORE any check so every rule sees the battle-tested canonical type and
# stays fully strict (a broken `ic_eeprom` becomes `ic_memory` and still fails its
# bypass-cap rule). This recognizes valid parts WITHOUT weakening any safety rule.
#
# Only exact-equivalent synonyms are folded here. Genuinely distinct types
# (ic_battery_charger, ic_protection) are added to the registry/schema instead, so
# they keep their own identity and the correct IC_TYPES_WITH_VCC treatment.
TYPE_ALIASES: dict[str, str] = {
    "voltage_ref":       "ic_voltage_ref",   # shunt reference (T3-37), not a VCC IC
    "polyfuse":          "fuse",             # resettable PPTC = a fuse for ERC
    "bjt_npn":           "transistor_npn",   # synonym
    "transistor":        "mosfet_n",         # corpus uses it only for G/D/S NMOS switches
    "ic_eeprom":         "ic_memory",        # registry ic_memory = "EEPROM, Flash, SRAM"
    "ic_display_driver": "ic_driver",        # display driver = driver IC
}


def _normalize_component_types(circuit: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy with synonym component types folded to canonical ones.
    Never mutates the caller's dict; structure/indices are unchanged so diagnostic
    paths stay valid."""
    if not TYPE_ALIASES:
        return circuit
    out = copy.deepcopy(circuit)
    comps = out.get("STAGE_1_TOPOLOGY", {}).get("components", [])
    for comp in comps:
        t = comp.get("type")
        if t in TYPE_ALIASES:
            comp["type"] = TYPE_ALIASES[t]
    return out


def _analyzer_error_item(group_name: str, exc: Exception) -> dict[str, Any]:
    """Blocking diagnostic for an analysis group that raised on malformed input."""
    return _base_item(
        code="ERC_ANALYZER_ERROR",
        path="$",
        message=f"analysis group '{group_name}' could not evaluate this circuit "
                f"({type(exc).__name__})",
        why_it_matters="A circuit that cannot be analyzed is malformed and cannot be "
                       "certified ERC-clean.",
        repair_hint="Return well-formed circuit JSON matching the schema (components "
                    "with id/type, nets with pins).",
        related_rule="ERC-ROBUST",
    )


def analyze_schematic(circuit: dict[str, Any]) -> dict[str, Any]:
    """Return structured static diagnostics for one circuit-like object.

    Robust to arbitrary / malformed input: callers (the STaR harvest and the prod
    correction loop) feed model-generated JSON through here, so NO analysis group may
    raise. A group that fails on a malformed circuit yields a blocking diagnostic
    instead, keeping the circuit (correctly) invalid without crashing the caller.
    """
    try:
        circuit = _normalize_component_types(circuit)
    except Exception:  # noqa: BLE001 — robustness boundary
        circuit = circuit if isinstance(circuit, dict) else {}
    diagnostics: list[dict[str, Any]] = []
    for group in (_forbidden_field_diagnostics, _validator_diagnostics):
        try:
            diagnostics.extend(group(circuit))
        except Exception as exc:  # noqa: BLE001 — robustness boundary
            diagnostics.append(_analyzer_error_item(getattr(group, "__name__", "group"), exc))
    try:
        diagnostics.extend(diagnostic_rules.electrical_diagnostics(circuit, _base_item))
    except Exception as exc:  # noqa: BLE001 — robustness boundary
        diagnostics.append(_analyzer_error_item("electrical_diagnostics", exc))
    return {
        "valid": not diagnostics,
        "diagnostics": diagnostics,
        "diagnostic_count": len(diagnostics),
    }


def analyze_fixture(name: str) -> dict[str, Any]:
    fixtures = {
        "button_without_pull": _fixture_button_without_pull,
        "floating_mosfet_gate": _fixture_floating_mosfet_gate,
        "ic_not_on_literal_vcc": _fixture_ic_not_on_literal_vcc,
        "ic_without_vcc_bypass": _fixture_ic_without_vcc_bypass,
        "isolated_component": _fixture_isolated_component,
        "led_without_resistor": _fixture_led_without_resistor,
        "reversed_capacitor": _fixture_reversed_capacitor,
        "short_vcc_gnd": _fixture_short_vcc_gnd,
    }
    if name not in fixtures:
        raise ValueError(f"unknown diagnostic fixture: {name}")
    return analyze_schematic(fixtures[name]())


def coverage_report(taxonomy_path: Path = DEFAULT_TAXONOMY_PATH) -> dict[str, Any]:
    taxonomy = _load_taxonomy(taxonomy_path)
    registry = sorted(validate.load_registry_component_types(REGISTRY_PATH))
    covered = sorted(component_type for component_type in registry if component_type in COMPONENT_CARDS)
    return {
        "taxonomy_version": taxonomy.get("version", "unknown"),
        "diagnostic_codes": sorted(taxonomy.get("codes", {})),
        "registry_component_types": len(registry),
        "component_type_coverage": covered,
        "missing_component_types": sorted(set(registry) - set(covered)),
        "coverage_basis": "registry-aware schema diagnostics, forbidden-field checks, and interaction diagnostics",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument("--coverage-report", type=Path)
    args = parser.parse_args(argv)

    report = coverage_report(args.taxonomy)
    if args.coverage_report:
        args.coverage_report.parent.mkdir(parents=True, exist_ok=True)
        args.coverage_report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not report["missing_component_types"] else 1


def build_retry_feedback(report: dict[str, Any], max_items: int = 8) -> dict[str, Any]:
    repairs = []
    for item in report.get("diagnostics", [])[:max_items]:
        repairs.append({
            "code": item.get("code", ""),
            "path": item.get("path", ""),
            "component_id": item.get("component_id", ""),
            "component_type": item.get("component_type", ""),
            "pin_ref": item.get("pin_ref", ""),
            "net_name": item.get("net_name", ""),
            "problem": item.get("message", ""),
            "expected": item.get("expected", ""),
            "actual": item.get("actual", ""),
            "repair_hint": item.get("repair_hint", ""),
            "related_rule": item.get("related_rule", ""),
        })
    return {
        "format": "ohmatic_diagnostic_feedback_v1",
        "valid": bool(report.get("valid", False)),
        "diagnostic_count": int(report.get("diagnostic_count", len(report.get("diagnostics", [])))),
        "instruction": "Revise the circuit JSON only. Fix each repair item and return strict Ohmatic v0.1 JSON with no markdown or reasoning.",
        "repairs": repairs,
    }


def _load_taxonomy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_item(
    *,
    code: str,
    path: str,
    message: str,
    why_it_matters: str,
    expected: Any = "",
    actual: Any = "",
    repair_hint: str,
    component_id: str = "",
    component_type: str = "",
    pin_ref: str = "",
    net_name: str = "",
    related_component_cards: list[str] | None = None,
    related_rule: str,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "path": path,
        "message": message,
        "why_it_matters": why_it_matters,
        "expected": expected,
        "actual": actual,
        "repair_hint": repair_hint,
        "component_id": component_id,
        "component_type": component_type,
        "pin_ref": pin_ref,
        "net_name": net_name,
        "related_component_cards": related_component_cards or [],
        "related_rule": related_rule,
    }


def _forbidden_field_diagnostics(value: Any, path: str = "$") -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if path.endswith(".pins"):
            return items
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if validate.is_forbidden_field(key):
                items.append(_base_item(
                    code="FORBIDDEN_SUPPLIER_FIELD",
                    path=child_path,
                    message=f"forbidden Step 2 supplier/BOM-style field '{key}'",
                    why_it_matters="Step 2 parser data must stay local and deterministic with no supplier, pricing, stock, URL, or API-key surface.",
                    expected="no supplier/BOM/API fields anywhere in circuit JSON",
                    actual=key,
                    repair_hint="Remove the field; Step 2 may only emit circuit JSON and local deterministic metadata.",
                    related_rule="STEP2-FORBID-SUPPLIER",
                ))
            items.extend(_forbidden_field_diagnostics(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(_forbidden_field_diagnostics(child, f"{path}[{index}]"))
    return items


def _validator_diagnostics(circuit: dict[str, Any]) -> list[dict[str, Any]]:
    errors = validate.validate_circuit(circuit, registry_path=REGISTRY_PATH)
    return [_diagnostic_from_validator_error(error, circuit) for error in errors]


# ── Validator-error → diagnostic dispatch ─────────────────────────────────────
# A flat, scannable table of (matcher, handler) pairs. _diagnostic_from_validator_error
# walks it top-to-bottom and the FIRST matching entry wins — match order is load-bearing
# (earlier patterns shadow later ones), so the order here MUST mirror the original ladder.
#
# matcher is either:
#   • a compiled regex   → handler runs on the first one whose .match(error) is truthy
#   • a literal str       → handler runs on exact equality (match passed as None)
# Regexes are compiled ONCE here, not per call. Each handler takes a small _Ctx and
# returns the kwargs for _base_item(); the WHY of each rule lives on its handler.


class _Ctx:
    """Per-error dispatch context: the raw error, the circuit, and the two path roots
    (computed once instead of re-deriving the STAGE_1_TOPOLOGY ternary per handler)."""

    __slots__ = ("error", "circuit", "comp_root", "net_root")

    def __init__(self, error: str, circuit: dict[str, Any]) -> None:
        self.error = error
        self.circuit = circuit
        self.comp_root = "$.STAGE_1_TOPOLOGY.components" if "STAGE_1_TOPOLOGY" in circuit else "$.components"
        self.net_root = "$.STAGE_1_TOPOLOGY.nets" if "STAGE_1_TOPOLOGY" in circuit else "$.nets"

# Unknown component type — unknown types can't be constrained by registry, cards, grammar, or verifier.
def _h_unknown_type(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id, component_type = m.groups()
    index = _component_index(ctx.circuit, component_id)
    return dict(
        code="REGISTRY_UNKNOWN_COMPONENT_TYPE",
        path=f"{ctx.comp_root}[{index}].type" if index >= 0 else f"{ctx.comp_root}[*].type",
        message=ctx.error,
        why_it_matters="Unknown component types cannot be constrained by the registry, component cards, grammar, or verifier.",
        expected=sorted(validate.load_registry_component_types(REGISTRY_PATH)),
        actual=component_type,
        repair_hint="Replace the component type with one from verifier/config/component_registry.toml.",
        component_id=component_id,
        component_type=component_type,
        related_rule="T1-PARSE-REGISTRY",
    )

# Unknown pin on a known component — a net pin ref must match a declared pin exactly.
def _h_unknown_pin(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    net_name, pin_name, component_id = m.groups()
    net_index, pin_index, pin_ref = _net_pin_location(ctx.circuit, net_name, component_id, pin_name)
    component_type = _component_type(ctx.circuit, component_id)
    return dict(
        code="PIN_UNKNOWN_FOR_COMPONENT",
        path=f"{ctx.net_root}[{net_index}].pins[{pin_index}]" if net_index >= 0 and pin_index >= 0 else f"{ctx.net_root}[*].pins[*]",
        message=ctx.error,
        why_it_matters="A net pin reference must match a declared component pin exactly or the circuit cannot be mapped to a schematic.",
        expected=sorted(_component_pins(ctx.circuit, component_id)),
        actual=pin_name,
        repair_hint="Use one of the declared pin names on the referenced component.",
        component_id=component_id,
        component_type=component_type,
        pin_ref=pin_ref,
        net_name=net_name,
        related_component_cards=[component_type] if component_type else [],
        related_rule="T1-07",
    )

# Net references unknown component — an unresolved ref makes the netlist unroutable.
def _h_unknown_comp_ref(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    net_name, component_id = m.groups()
    component_id = component_id.strip()
    return dict(
        code="NET_UNKNOWN_COMPONENT_REF",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="Every pin reference in a net must resolve to a declared component; an unresolved reference makes the netlist unroutable.",
        expected="a component id declared in STAGE_1_TOPOLOGY.components",
        actual=component_id,
        repair_hint=(
            f"Add a component with id '{component_id}' to STAGE_1_TOPOLOGY.components, "
            f"or remove '{component_id}' from net '{net_name}'.pins so every net pin points "
            f"at a declared component."
        ),
        component_id=component_id,
        net_name=net_name,
        related_rule="T1-06",
    )

# Spatial node has no matching topology component — orphan nodes break layout rendering.
def _h_spatial_no_topo(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    node_id = m.group(1)
    return dict(
        code="SPATIAL_NODE_MISSING_TOPOLOGY_COMPONENT",
        path="$.STAGE_2_LAYOUT.spatial_nodes",
        message=ctx.error,
        why_it_matters="Every STAGE_2_LAYOUT spatial node must map 1:1 to a STAGE_1_TOPOLOGY component; orphan nodes break layout rendering.",
        expected="a STAGE_1_TOPOLOGY component with the same id",
        actual=node_id,
        repair_hint=(
            f"Add a STAGE_1_TOPOLOGY component with id '{node_id}', "
            f"or delete the STAGE_2_LAYOUT.spatial_nodes entry '{node_id}'. "
            f"Every spatial node must map 1:1 to a component."
        ),
        component_id=node_id,
        related_rule="T1-LAYOUT",
    )

# Topology component missing spatial node — renderer needs coordinates for every component.
def _h_topo_no_spatial(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id = m.group(1)
    return dict(
        code="TOPOLOGY_COMPONENT_MISSING_SPATIAL_NODE",
        path="$.STAGE_2_LAYOUT.spatial_nodes",
        message=ctx.error,
        why_it_matters="Every topology component must have coordinates in STAGE_2_LAYOUT so the schematic renderer can place it.",
        expected=f"a spatial_nodes entry with id '{component_id}'",
        actual="(missing)",
        repair_hint=(
            f"Add {{\"id\": \"{component_id}\", \"x\": <number>, \"y\": <number>}} "
            f"to STAGE_2_LAYOUT.spatial_nodes."
        ),
        component_id=component_id,
        related_rule="T1-LAYOUT",
    )

# Missing required power_vcc — without it ERC cannot verify IC power or voltage rails.
def _h_missing_vcc(m, ctx: _Ctx) -> dict[str, Any]:
    return dict(
        code="MISSING_POWER_VCC",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters="Every circuit must have a power_vcc component to anchor the positive supply rail; without it ERC cannot verify IC power or voltage rails.",
        expected="at least one component with type 'power_vcc'",
        actual="(none found)",
        repair_hint=(
            "Add a component of type 'power_vcc' (e.g. "
            "{\"id\": \"VCC1\", \"type\": \"power_vcc\", \"value\": \"5V\", "
            "\"part\": \"VCC\", \"pins\": {\"1\": \"VCC\"}}) "
            "and connect it to the VCC net."
        ),
        related_rule="T1-POWER",
    )

# Missing required power_gnd — without it ERC cannot verify return paths.
def _h_missing_gnd(m, ctx: _Ctx) -> dict[str, Any]:
    return dict(
        code="MISSING_POWER_GND",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters="Every circuit must have a power_gnd component to anchor the ground reference; without it ERC cannot verify return paths.",
        expected="at least one component with type 'power_gnd'",
        actual="(none found)",
        repair_hint=(
            "Add a component of type 'power_gnd' (e.g. "
            "{\"id\": \"GND1\", \"type\": \"power_gnd\", \"value\": \"0V\", "
            "\"part\": \"GND\", \"pins\": {\"1\": \"GND\"}}) "
            "and connect it to the GND net."
        ),
        related_rule="T1-POWER",
    )

# Missing 'metadata' — required block carrying title/description/version/tags for the pipeline.
def _h_missing_metadata(m, ctx: _Ctx) -> dict[str, Any]:
    return dict(
        code="MISSING_METADATA",
        path="$.metadata",
        message=ctx.error,
        why_it_matters="The metadata block is required; it carries title, description, version, and tags used by the corpus pipeline.",
        expected="a 'metadata' object with fields: title, description, version, tags",
        actual="(missing)",
        repair_hint=(
            "Add a top-level 'metadata' key: "
            "{\"title\": \"<name>\", \"description\": \"<one sentence>\", "
            "\"version\": \"0.1\", \"tags\": [\"<tag>\"]}."
        ),
        related_rule="T1-META",
    )

# metadata missing required fields — incomplete metadata blocks the pipeline and data builder.
def _h_meta_missing_fields(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    fields_str = m.group(1)
    return dict(
        code="METADATA_MISSING_FIELDS",
        path="$.metadata",
        message=ctx.error,
        why_it_matters="Incomplete metadata blocks the corpus pipeline and training data builder.",
        expected="all of: title, description, version, tags",
        actual=f"missing {fields_str}",
        repair_hint=(
            f"Add the missing fields {fields_str} to the metadata object. "
            "Required shape: {\"title\": str, \"description\": str, \"version\": \"0.1\", \"tags\": [str]}."
        ),
        related_rule="T1-META",
    )

# version must be '0.1' — exact string required by validator and data builder.
def _h_bad_version(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    actual_ver = m.group(1)
    return dict(
        code="METADATA_BAD_VERSION",
        path="$.metadata.version",
        message=ctx.error,
        why_it_matters="The schema version field must be exactly '0.1' to pass the corpus validator and training data builder.",
        expected="0.1",
        actual=actual_ver,
        repair_hint="Set metadata.version to the string \"0.1\" (not a number, not any other value).",
        related_rule="T1-META",
    )

# component id violates pattern — ids must follow ^[A-Z][A-Za-z0-9_]*$ so pin refs parse.
def _h_bad_id_pattern(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id = m.group(1)
    return dict(
        code="COMPONENT_ID_PATTERN_VIOLATION",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters="Component ids must follow ^[A-Z][A-Za-z0-9_]*$ so net pin refs (e.g. R1.1) parse unambiguously.",
        expected="^[A-Z][A-Za-z0-9_]*$ (start uppercase, then alphanumeric or underscore)",
        actual=component_id,
        repair_hint=(
            f"Rename component '{component_id}' so the id starts with an uppercase letter "
            f"and contains only letters, digits, and underscores "
            f"(e.g. '{component_id[0].upper() + component_id[1:] if component_id else 'X1'}')."
        ),
        component_id=component_id,
        related_rule="T1-05",
    )

# Duplicate component id — duplicate ids make pin refs ambiguous and fail validation.
def _h_dup_comp_id(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id = m.group(1).strip()
    return dict(
        code="DUPLICATE_COMPONENT_ID",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters="Duplicate component ids make net pin references ambiguous and cause netlist validation to fail.",
        expected="unique ids across all components",
        actual=component_id,
        repair_hint=(
            f"Rename one of the duplicate '{component_id}' components to a unique id "
            f"(e.g. append a number suffix), then update all net pin refs that reference it."
        ),
        component_id=component_id,
        related_rule="T1-05",
    )

# component[i] missing 'id' — every component needs a string id so nets can reference its pins.
def _h_comp_missing_id(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    index = int(m.group(1))
    return dict(
        code="COMPONENT_MISSING_ID",
        path=(
            f"$.STAGE_1_TOPOLOGY.components[{index}]"
            if "STAGE_1_TOPOLOGY" in ctx.circuit
            else f"$.components[{index}]"
        ),
        message=ctx.error,
        why_it_matters="Every component must have a string 'id' field so nets can reference its pins.",
        expected="a non-empty string id starting with an uppercase letter",
        actual="(missing)",
        repair_hint=(
            f"Add an 'id' field to components[{index}] "
            f"(e.g. \"id\": \"R{index + 1}\"). "
            "The id must match ^[A-Z][A-Za-z0-9_]*$."
        ),
        related_rule="T1-05",
    )

# component 'X' missing 'field' — per-field repair hints for required component fields.
def _h_comp_missing_field(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id, field_name = m.groups()
    field_hints = {
        "type":  "Set 'type' to a valid component type from verifier/config/component_registry.toml.",
        "value": "Set 'value' to a string describing the component value (e.g. \"10k\", \"100nF\", \"5V\").",
        "part":  "Set 'part' to a string identifying the package/part (e.g. \"0603\", \"SOT-23\", \"DIP-8\").",
        "pins":  "Add a 'pins' dict mapping each pin name to its net name (e.g. {\"1\": \"VCC\", \"2\": \"GND\"}).",
        "x":     "Add an 'x' coordinate (number) for the component position in the flat schematic format.",
        "y":     "Add an 'y' coordinate (number) for the component position in the flat schematic format.",
    }
    hint = field_hints.get(field_name, f"Add the required '{field_name}' field to component '{component_id}'.")
    return dict(
        code="COMPONENT_MISSING_FIELD",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters=f"The '{field_name}' field is required on every component for schema compliance and netlist routing.",
        expected=f"'{field_name}' field present",
        actual="(missing)",
        repair_hint=hint,
        component_id=component_id,
        related_rule="T1-05",
    )

# component 'X' has unexpected fields — strict schema rejects extras (may carry supplier/BOM data).
def _h_comp_unexpected_fields(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id, fields_str = m.groups()
    return dict(
        code="COMPONENT_UNEXPECTED_FIELDS",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters="Extra fields on components are rejected by the strict schema validator and may carry forbidden supplier/BOM data.",
        expected="only: id, type, value, part, pins (plus x, y in flat format)",
        actual=fields_str,
        repair_hint=f"Remove the unexpected fields {fields_str} from component '{component_id}'.",
        component_id=component_id,
        related_rule="T1-05",
    )

# component 'X' has x/y in STAGE_1_TOPOLOGY — coordinates belong only in STAGE_2_LAYOUT.
def _h_comp_xy_in_topo(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id = m.group(1)
    return dict(
        code="COMPONENT_COORDS_IN_TOPOLOGY",
        path="$.STAGE_1_TOPOLOGY.components",
        message=ctx.error,
        why_it_matters="In the two-stage format, x/y coordinates belong only in STAGE_2_LAYOUT.spatial_nodes, not on topology components.",
        expected="no x/y on STAGE_1_TOPOLOGY components",
        actual="x and/or y present on component",
        repair_hint=(
            f"Remove 'x' and 'y' from STAGE_1_TOPOLOGY component '{component_id}' "
            f"and put them in STAGE_2_LAYOUT.spatial_nodes as "
            f"{{\"id\": \"{component_id}\", \"x\": <number>, \"y\": <number>}}."
        ),
        component_id=component_id,
        related_rule="T1-LAYOUT",
    )

# component 'X' pins must be dict — pins map pin names to net names so nets can reference them.
def _h_comp_pins_dict(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id = m.group(1)
    return dict(
        code="COMPONENT_PINS_NOT_DICT",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters="Pins must be a JSON object mapping pin names to net names so nets can reference them.",
        expected="a JSON object like {\"1\": \"VCC\", \"2\": \"GND\"}",
        actual="non-dict value",
        repair_hint=f"Replace 'pins' on component '{component_id}' with a dict mapping pin names to net names.",
        component_id=component_id,
        related_rule="T1-05",
    )

# component 'X' pins must not be empty — a pin-less component is unreachable by the netlist.
def _h_comp_pins_empty(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    component_id = m.group(1)
    return dict(
        code="COMPONENT_PINS_EMPTY",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters="A component with no pins cannot be connected to any net and is unreachable by the netlist.",
        expected="at least one pin in the pins dict",
        actual="{}",
        repair_hint=(
            f"Add at least one pin to component '{component_id}'.pins "
            f"(e.g. {{\"1\": \"VCC\", \"2\": \"GND\"}})."
        ),
        component_id=component_id,
        related_rule="T1-05",
    )

# component pin not connected to any net — every declared pin must appear in exactly one net.
def _h_pin_not_connected(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    pin_ref = m.group(1)
    component_id, _pin_name = pin_ref.split(".", 1)
    return dict(
        code="UNCONNECTED_PIN",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="Every declared component pin must appear in exactly one net; unconnected pins indicate an incomplete netlist.",
        expected=f"pin '{pin_ref}' referenced in at least one net",
        actual="(not referenced in any net)",
        repair_hint=(
            f"Add '{pin_ref}' to an appropriate net's pins list, "
            f"or if the pin is intentionally unused add it to a dedicated 'NC' net."
        ),
        component_id=component_id,
        pin_ref=pin_ref,
        related_rule="T1-CONNECTIVITY",
    )

# pin ref appears in more than one net — a pin in two nets is an electrical short.
def _h_short_ref(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    pin_ref = m.group(1)
    component_id, _pin_name = pin_ref.split(".", 1)
    return dict(
        code="PIN_SHORT_ACROSS_NETS",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="A pin appearing in two nets creates an electrical short that would destroy components in a real circuit.",
        expected=f"pin '{pin_ref}' referenced in exactly one net",
        actual="referenced in more than one net",
        repair_hint=(
            f"Remove '{pin_ref}' from all but one net. "
            f"If the intent is to bridge two signals, merge those nets into one."
        ),
        component_id=component_id,
        pin_ref=pin_ref,
        related_rule="T1-SHORT",
    )

# net 'X' missing 'pins' field — a net without a pins list describes no connections.
def _h_net_missing_pins(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    net_name = m.group(1)
    return dict(
        code="NET_MISSING_PINS",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="A net without a 'pins' list cannot describe any connections; the netlist is incomplete.",
        expected="a 'pins' list with at least 2 pin refs",
        actual="(missing)",
        repair_hint=f"Add a 'pins' list to net '{net_name}' with at least 2 pin refs like [\"C1.1\", \"U1.VCC\"].",
        net_name=net_name,
        related_rule="T1-06",
    )

# net 'X' fewer than 2 pins — a net with <2 pins connects nothing.
def _h_net_too_few_pins(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    net_name, count = m.groups()
    return dict(
        code="NET_TOO_FEW_PINS",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="A net with fewer than 2 pins connects nothing; every net must join at least 2 component pins.",
        expected="at least 2 pin refs in the net",
        actual=f"{count} pin(s)",
        repair_hint=(
            f"Add more pin refs to net '{net_name}'.pins so it has at least 2 entries, "
            f"or remove the net if it is not needed."
        ),
        net_name=net_name,
        related_rule="T1-06",
    )

# Duplicate net name — duplicate names are ambiguous and make the netlist unroutable.
def _h_net_dup_name(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    net_name = m.group(1).strip()
    return dict(
        code="DUPLICATE_NET_NAME",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="Duplicate net names are ambiguous and make the netlist unroutable.",
        expected="unique net names",
        actual=net_name,
        repair_hint=(
            f"Merge the two '{net_name}' nets into one (combine their pin lists), "
            f"or rename one to a distinct name."
        ),
        net_name=net_name,
        related_rule="T1-06",
    )

# net 'X' invalid pin ref — pin refs must match ComponentId.pin so they can be split.
def _h_invalid_pin_ref(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    net_name, bad_ref = m.groups()
    bad_ref = bad_ref.strip()
    return dict(
        code="NET_INVALID_PIN_REF",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="Pin refs must match ^[A-Z][A-Za-z0-9_]*\\.[A-Za-z0-9_+\\-]+$ so they can be split into component_id.pin_name.",
        expected="format ComponentId.pin (e.g. 'R1.1', 'U1.VCC')",
        actual=bad_ref,
        repair_hint=(
            f"Replace '{bad_ref}' in net '{net_name}'.pins with a valid pin ref "
            f"in the form 'ComponentId.pin_name' where ComponentId starts with an uppercase letter."
        ),
        net_name=net_name,
        related_rule="T1-06",
    )

# net 'X' contains duplicate pin ref — a pin twice in one net is redundant (copy-paste error).
def _h_dup_pin_ref(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    net_name, pin_ref = m.groups()
    pin_ref = pin_ref.strip()
    return dict(
        code="NET_DUPLICATE_PIN_REF",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="A pin appearing twice in the same net is redundant and may indicate a copy-paste error.",
        expected=f"each pin ref appears at most once in net '{net_name}'",
        actual=f"'{pin_ref}' listed more than once",
        repair_hint=f"Remove the duplicate '{pin_ref}' entry from net '{net_name}'.pins, keeping only one occurrence.",
        net_name=net_name,
        pin_ref=pin_ref,
        related_rule="T1-06",
    )

# spatial_nodes duplicate id — each component maps to exactly one position.
def _h_spatial_dup(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    node_id = m.group(1)
    return dict(
        code="SPATIAL_NODES_DUPLICATE_ID",
        path="$.STAGE_2_LAYOUT.spatial_nodes",
        message=ctx.error,
        why_it_matters="Duplicate spatial node ids make layout rendering ambiguous; each component maps to exactly one position.",
        expected="unique ids across all spatial_nodes",
        actual=node_id,
        repair_hint=f"Remove the duplicate STAGE_2_LAYOUT.spatial_nodes entry with id '{node_id}', keeping only one.",
        component_id=node_id,
        related_rule="T1-LAYOUT",
    )

# STAGE_1_TOPOLOGY must be a JSON object — must hold 'components' and 'nets' arrays.
def _h_stage1_not_object(m, ctx: _Ctx) -> dict[str, Any]:
    return dict(
        code="STAGE1_NOT_OBJECT",
        path="$.STAGE_1_TOPOLOGY",
        message=ctx.error,
        why_it_matters="STAGE_1_TOPOLOGY must be a JSON object containing 'components' and 'nets' arrays.",
        expected="a JSON object {\"components\": [...], \"nets\": [...]}",
        actual="non-object value",
        repair_hint="Replace STAGE_1_TOPOLOGY with a JSON object: {\"components\": [...], \"nets\": [...]}.",
        related_rule="T1-FORMAT",
    )

# STAGE_2_LAYOUT must be a JSON object — must hold the 'spatial_nodes' array.
def _h_stage2_not_object(m, ctx: _Ctx) -> dict[str, Any]:
    return dict(
        code="STAGE2_NOT_OBJECT",
        path="$.STAGE_2_LAYOUT",
        message=ctx.error,
        why_it_matters="STAGE_2_LAYOUT must be a JSON object containing the 'spatial_nodes' array.",
        expected="a JSON object {\"spatial_nodes\": [...]}",
        actual="non-object value",
        repair_hint="Replace STAGE_2_LAYOUT with a JSON object: {\"spatial_nodes\": [{\"id\": \"...\", \"x\": 0, \"y\": 0}, ...]}.",
        related_rule="T1-FORMAT",
    )

# 'components' must be a non-empty list — a circuit with no components is meaningless.
def _h_components_empty(m, ctx: _Ctx) -> dict[str, Any]:
    return dict(
        code="COMPONENTS_EMPTY_OR_MISSING",
        path=ctx.comp_root,
        message=ctx.error,
        why_it_matters="A circuit with no components is meaningless; at minimum power_vcc, power_gnd, and one load component are required.",
        expected="a non-empty list of component objects",
        actual="empty list or non-list",
        repair_hint=(
            "Set 'components' to a non-empty list. Every circuit needs at least "
            "power_vcc, power_gnd, and one functional component."
        ),
        related_rule="T1-05",
    )

# 'nets' must be a non-empty list — a circuit with no nets has no connections.
def _h_nets_empty(m, ctx: _Ctx) -> dict[str, Any]:
    return dict(
        code="NETS_EMPTY_OR_MISSING",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="A circuit with no nets has no connections; at minimum VCC and GND nets are required.",
        expected="a non-empty list of net objects",
        actual="empty list or non-list",
        repair_hint=(
            "Set 'nets' to a non-empty list. Every circuit needs at least VCC and GND nets "
            "with pin refs connecting the power components."
        ),
        related_rule="T1-06",
    )

# net 'X' has unexpected fields — strict schema rejects extras (nets allow only name, pins).
def _h_net_unexpected(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    net_name, fields_str = m.groups()
    return dict(
        code="NET_UNEXPECTED_FIELDS",
        path=ctx.net_root,
        message=ctx.error,
        why_it_matters="Extra fields on nets are rejected by the strict schema validator.",
        expected="only: name, pins",
        actual=fields_str,
        repair_hint=f"Remove the unexpected fields {fields_str} from net '{net_name}'. Nets only allow 'name' and 'pins'.",
        net_name=net_name,
        related_rule="T1-06",
    )

# spatial_nodes 'X' has unexpected fields — strict schema rejects extras (only id, x, y).
def _h_spatial_unexpected(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    node_id, fields_str = m.groups()
    return dict(
        code="SPATIAL_NODE_UNEXPECTED_FIELDS",
        path="$.STAGE_2_LAYOUT.spatial_nodes",
        message=ctx.error,
        why_it_matters="Extra fields on spatial nodes are rejected by the strict schema validator.",
        expected="only: id, x, y",
        actual=fields_str,
        repair_hint=f"Remove the unexpected fields {fields_str} from STAGE_2_LAYOUT.spatial_nodes entry '{node_id}'.",
        component_id=node_id,
        related_rule="T1-LAYOUT",
    )

# Forbidden supplier/BOM field — these must never appear in Step 2 circuit JSON.
def _h_forbidden_field(m: "re.Match", ctx: _Ctx) -> dict[str, Any]:
    field_path, field_name = m.groups()
    field_name = field_name.strip()
    return dict(
        code="FORBIDDEN_SUPPLIER_FIELD",
        path=field_path.strip(),
        message=ctx.error,
        why_it_matters="Supplier/BOM/API-key fields must never appear in Step 2 circuit JSON; they leak external dependencies into local deterministic data.",
        expected="no supplier/BOM/API fields",
        actual=field_name,
        repair_hint=f"Remove the '{field_name}' field at {field_path.strip()}. Step 2 may only contain circuit structure.",
        related_rule="STEP2-FORBID-SUPPLIER",
    )

# Catch-all — fires when nothing above matched (should now rarely happen).
def _h_catch_all(m, ctx: _Ctx) -> dict[str, Any]:
    return dict(
        code="SCHEMA_VALIDATION_ERROR",
        path="$",
        message=ctx.error,
        why_it_matters="The circuit must satisfy Ohmatic v0.1 structural rules before it can enter training or runtime verification.",
        expected="valid Ohmatic v0.1 circuit",
        actual=ctx.error,
        repair_hint="Correct the schema, component, pin, or net issue described in the message.",
        related_rule="T1",
    )

# (matcher, handler) in original ladder ORDER — first match wins. A compiled regex
# matches via .match(error); a literal str matches on exact equality.
_VALIDATOR_HANDLERS: tuple[tuple[Any, Any], ...] = (
    (re.compile(r"component '([^']+)' invalid type: (.+)"), _h_unknown_type),
    (re.compile(r"net '([^']+)' references unknown pin ([^ ]+) on ([A-Za-z0-9_]+)"), _h_unknown_pin),
    (re.compile(r"net '([^']+)' references unknown component: (.+)"), _h_unknown_comp_ref),
    (re.compile(r"spatial_nodes '([^']+)' has no matching component in STAGE_1_TOPOLOGY"), _h_spatial_no_topo),
    (re.compile(r"component '([^']+)' has no entry in STAGE_2_LAYOUT\.spatial_nodes"), _h_topo_no_spatial),
    ("Missing required power_vcc component", _h_missing_vcc),
    ("Missing required power_gnd component", _h_missing_gnd),
    ("Missing 'metadata' field", _h_missing_metadata),
    (re.compile(r"metadata missing required fields: (\[.+\])"), _h_meta_missing_fields),
    (re.compile(r"version must be '0\.1', got '([^']*)'"), _h_bad_version),
    (re.compile(r"component '([^']+)' id violates pattern \^.+\$"), _h_bad_id_pattern),
    (re.compile(r"Duplicate component id: (.+)"), _h_dup_comp_id),
    (re.compile(r"component\[(\d+)\] missing 'id'"), _h_comp_missing_id),
    (re.compile(r"component '([^']+)' missing '([^']+)'"), _h_comp_missing_field),
    (re.compile(r"component '([^']+)' has unexpected fields: (\[.+\])"), _h_comp_unexpected_fields),
    (re.compile(r"component '([^']+)' has x/y in STAGE_1_TOPOLOGY"), _h_comp_xy_in_topo),
    (re.compile(r"component '([^']+)' pins must be dict"), _h_comp_pins_dict),
    (re.compile(r"component '([^']+)' pins must not be empty"), _h_comp_pins_empty),
    (re.compile(r"component pin ([A-Za-z0-9_]+\.[A-Za-z0-9_+\-]+) not connected to any net"), _h_pin_not_connected),
    (re.compile(r"pin ref ([A-Za-z0-9_]+\.[A-Za-z0-9_+\-]+) appears in more than one net \(electrical short\)"), _h_short_ref),
    (re.compile(r"net '([^']+)' missing 'pins' field"), _h_net_missing_pins),
    (re.compile(r"net '([^']+)' must have at least 2 pins, got (\d+)"), _h_net_too_few_pins),
    (re.compile(r"Duplicate net name: (.+)"), _h_net_dup_name),
    (re.compile(r"net '([^']+)' invalid pin ref: (.+)"), _h_invalid_pin_ref),
    (re.compile(r"net '([^']+)' contains duplicate pin ref: (.+)"), _h_dup_pin_ref),
    (re.compile(r"spatial_nodes: duplicate id '([^']+)'"), _h_spatial_dup),
    ("STAGE_1_TOPOLOGY must be a JSON object", _h_stage1_not_object),
    ("STAGE_2_LAYOUT must be a JSON object", _h_stage2_not_object),
    ("'components' must be a non-empty list", _h_components_empty),
    ("'nets' must be a non-empty list", _h_nets_empty),
    (re.compile(r"net '([^']+)' has unexpected fields: (\[.+\])"), _h_net_unexpected),
    (re.compile(r"spatial_nodes '([^']+)' has unexpected fields: (\[.+\])"), _h_spatial_unexpected),
    (re.compile(r"forbidden field at ([^:]+): (.+)"), _h_forbidden_field),
)


def _diagnostic_from_validator_error(error: str, circuit: dict[str, Any]) -> dict[str, Any]:
    ctx = _Ctx(error, circuit)
    for matcher, handler in _VALIDATOR_HANDLERS:
        if isinstance(matcher, str):
            if error == matcher:
                return _base_item(**handler(None, ctx))
        else:
            m = matcher.match(error)
            if m:
                return _base_item(**handler(m, ctx))
    return _base_item(**_h_catch_all(None, ctx))


def _circuit_components(circuit: dict[str, Any]) -> list[dict[str, Any]]:
    """Return component list from either flat or STAGE_1_TOPOLOGY format."""
    if "STAGE_1_TOPOLOGY" in circuit:
        return circuit["STAGE_1_TOPOLOGY"].get("components", [])
    return circuit.get("components", [])


def _circuit_nets(circuit: dict[str, Any]) -> list[dict[str, Any]]:
    """Return nets list from either flat or STAGE_1_TOPOLOGY format."""
    if "STAGE_1_TOPOLOGY" in circuit:
        return circuit["STAGE_1_TOPOLOGY"].get("nets", [])
    return circuit.get("nets", [])


def _component_index(circuit: dict[str, Any], component_id: str) -> int:
    for index, component in enumerate(_circuit_components(circuit)):
        if isinstance(component, dict) and component.get("id") == component_id:
            return index
    return -1


def _component_type(circuit: dict[str, Any], component_id: str) -> str:
    for component in _circuit_components(circuit):
        if isinstance(component, dict) and component.get("id") == component_id:
            return str(component.get("type", ""))
    return ""


def _component_pins(circuit: dict[str, Any], component_id: str) -> set[str]:
    for component in _circuit_components(circuit):
        if isinstance(component, dict) and component.get("id") == component_id and isinstance(component.get("pins"), dict):
            return set(component["pins"])
    return set()


def _net_pin_location(circuit: dict[str, Any], net_name: str, component_id: str, pin_name: str) -> tuple[int, int, str]:
    target = f"{component_id}.{pin_name}"
    for net_index, net in enumerate(_circuit_nets(circuit)):
        if not isinstance(net, dict) or net.get("name") != net_name:
            continue
        for pin_index, pin_ref in enumerate(net.get("pins", [])):
            if pin_ref == target:
                return net_index, pin_index, target
    return -1, -1, target


def _fixture_led_without_resistor() -> dict[str, Any]:
    return {
        "metadata": {"title": "Bad LED", "description": "LED tied directly to VCC.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 80},
            {"id": "D1", "type": "led", "part": "0603", "value": "red", "pins": {"A": "VCC", "K": "GND"}, "x": 60, "y": 40},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "D1.A"]},
            {"name": "GND", "pins": ["GND1.1", "D1.K"]},
        ],
    }


def _fixture_short_vcc_gnd() -> dict[str, Any]:
    circuit = _fixture_led_without_resistor()
    circuit["metadata"]["title"] = "Bad Power Short"
    circuit["components"] = [
        {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "SHORT"}, "x": 0, "y": 0},
        {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "SHORT"}, "x": 0, "y": 80},
        {"id": "R1", "type": "resistor", "part": "0603", "value": "1k", "pins": {"1": "SHORT", "2": "NODE"}, "x": 60, "y": 40},
        {"id": "R2", "type": "resistor", "part": "0603", "value": "1k", "pins": {"1": "NODE", "2": "SHORT"}, "x": 100, "y": 40},
    ]
    circuit["nets"] = [
        {"name": "SHORT", "pins": ["VCC1.1", "GND1.1", "R1.1", "R2.2"]},
        {"name": "NODE", "pins": ["R1.2", "R2.1"]},
    ]
    return circuit


def _fixture_floating_mosfet_gate() -> dict[str, Any]:
    return {
        "metadata": {"title": "Bad Floating Gate", "description": "MOSFET gate only touches a capacitor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 100},
            {"id": "Q1", "type": "mosfet_n", "part": "SOT-23", "value": "logic", "pins": {"G": "GATE", "D": "VCC", "S": "GND"}, "x": 70, "y": 50},
            {"id": "C1", "type": "capacitor", "part": "0603", "value": "1nF", "pins": {"1": "GATE", "2": "GND"}, "x": 120, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "Q1.D"]},
            {"name": "GATE", "pins": ["Q1.G", "C1.1"]},
            {"name": "GND", "pins": ["GND1.1", "Q1.S", "C1.2"]},
        ],
    }


def _fixture_ic_without_vcc_bypass() -> dict[str, Any]:
    return {
        "metadata": {"title": "Bad IC No Bypass", "description": "Timer lacks VCC bypass capacitor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "U1", "type": "ic_timer", "part": "SOIC-8", "value": "555", "pins": {"VCC": "VCC", "GND": "GND", "TRIG": "TRIG", "OUT": "OUT", "RESET": "VCC", "CTRL": "CTRL", "THRESH": "TIM", "DISCH": "TIM"}, "x": 100, "y": 60},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "10k", "pins": {"1": "VCC", "2": "TRIG"}, "x": 55, "y": 40},
            {"id": "R2", "type": "resistor", "part": "0603", "value": "47k", "pins": {"1": "VCC", "2": "TIM"}, "x": 70, "y": 80},
            {"id": "C1", "type": "capacitor", "part": "0603", "value": "10nF", "pins": {"1": "CTRL", "2": "GND"}, "x": 150, "y": 80},
            {"id": "C2", "type": "capacitor", "part": "0603", "value": "1uF", "pins": {"1": "TIM", "2": "GND"}, "x": 160, "y": 100},
            {"id": "R3", "type": "resistor", "part": "0603", "value": "1k", "pins": {"1": "OUT", "2": "GND"}, "x": 180, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC", "U1.RESET", "R1.1", "R2.1"]},
            {"name": "TRIG", "pins": ["U1.TRIG", "R1.2"]},
            {"name": "TIM", "pins": ["U1.THRESH", "U1.DISCH", "R2.2", "C2.1"]},
            {"name": "CTRL", "pins": ["U1.CTRL", "C1.1"]},
            {"name": "OUT", "pins": ["U1.OUT", "R3.1"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "C1.2", "C2.2", "R3.2"]},
        ],
    }


def _fixture_ic_not_on_literal_vcc() -> dict[str, Any]:
    # A genuinely UNPOWERED IC: its supply pin connects to a plain net ("PWR") that
    # carries no power-rail symbol (power_vcc/3v3/5v/12v). T3-06 now recognizes any
    # positive supply rail (not just a net literally named "VCC"), so the only way to
    # trip it is a supply pin with no rail at all — which is what this fixture exercises.
    return {
        "metadata": {"title": "Bad IC No Supply Rail", "description": "IC supply pin not on any power rail.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "U1", "type": "ic_timer", "part": "SOIC-8", "value": "555", "pins": {"VCC": "PWR", "GND": "GND", "TRIG": "TRIG", "OUT": "OUT", "RESET": "PWR", "CTRL": "CTRL", "THRESH": "TIM", "DISCH": "TIM"}, "x": 100, "y": 60},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "10k", "pins": {"1": "PWR", "2": "TRIG"}, "x": 55, "y": 40},
            {"id": "R2", "type": "resistor", "part": "0603", "value": "47k", "pins": {"1": "PWR", "2": "TIM"}, "x": 70, "y": 80},
            {"id": "C1", "type": "capacitor", "part": "0603", "value": "10nF", "pins": {"1": "CTRL", "2": "GND"}, "x": 150, "y": 80},
            {"id": "C2", "type": "capacitor", "part": "0603", "value": "1uF", "pins": {"1": "TIM", "2": "GND"}, "x": 160, "y": 100},
            {"id": "R3", "type": "resistor", "part": "0603", "value": "1k", "pins": {"1": "OUT", "2": "GND"}, "x": 180, "y": 60},
        ],
        "nets": [
            {"name": "PWR", "pins": ["U1.VCC", "U1.RESET", "R1.1", "R2.1"]},
            {"name": "TRIG", "pins": ["U1.TRIG", "R1.2"]},
            {"name": "TIM", "pins": ["U1.THRESH", "U1.DISCH", "R2.2", "C2.1"]},
            {"name": "CTRL", "pins": ["U1.CTRL", "C1.1"]},
            {"name": "OUT", "pins": ["U1.OUT", "R3.1"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "C1.2", "C2.2", "R3.2"]},
        ],
    }


def _fixture_reversed_capacitor() -> dict[str, Any]:
    return {
        "metadata": {"title": "Bad Reversed Cap", "description": "Capacitor polarity is reversed.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 80},
            {"id": "C1", "type": "capacitor", "part": "0805", "value": "10uF", "pins": {"1": "GND", "2": "VCC"}, "x": 70, "y": 40},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "C1.2"]},
            {"name": "GND", "pins": ["GND1.1", "C1.1"]},
        ],
    }


def _fixture_button_without_pull() -> dict[str, Any]:
    return {
        "metadata": {"title": "Bad Button No Pull", "description": "Button output has no pull resistor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "3V3", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 100},
            {"id": "J1", "type": "connector", "part": "HEADER", "value": "", "pins": {"VCC": "VCC", "GND": "GND", "S1": "BTN", "S2": "GND"}, "x": 80, "y": 45},
            {"id": "SW1", "type": "button", "part": "TACT", "value": "", "pins": {"1": "BTN", "2": "GND"}, "x": 160, "y": 70},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "J1.VCC"]},
            {"name": "BTN", "pins": ["J1.S1", "SW1.1"]},
            {"name": "GND", "pins": ["GND1.1", "J1.GND", "J1.S2", "SW1.2"]},
        ],
    }


def _fixture_isolated_component() -> dict[str, Any]:
    return {
        "metadata": {"title": "Bad Isolated Island", "description": "Passive island is disconnected from power.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 100},
            {"id": "C1", "type": "capacitor", "part": "0603", "value": "100nF", "pins": {"1": "VCC", "2": "GND"}, "x": 60, "y": 50},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "10k", "pins": {"1": "ISO_A", "2": "ISO_B"}, "x": 160, "y": 50},
            {"id": "C2", "type": "capacitor", "part": "0603", "value": "1nF", "pins": {"1": "ISO_A", "2": "ISO_B"}, "x": 200, "y": 50},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "C1.1"]},
            {"name": "GND", "pins": ["GND1.1", "C1.2"]},
            {"name": "ISO_A", "pins": ["R1.1", "C2.1"]},
            {"name": "ISO_B", "pins": ["R1.2", "C2.2"]},
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
