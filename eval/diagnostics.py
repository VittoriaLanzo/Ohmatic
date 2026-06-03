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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def analyze_schematic(circuit: dict[str, Any]) -> dict[str, Any]:
    """Return structured static diagnostics for one circuit-like object."""
    circuit = _normalize_component_types(circuit)
    diagnostics: list[dict[str, Any]] = []
    diagnostics.extend(_forbidden_field_diagnostics(circuit))
    diagnostics.extend(_validator_diagnostics(circuit))
    diagnostics.extend(diagnostic_rules.electrical_diagnostics(circuit, _base_item))
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


def _diagnostic_from_validator_error(error: str, circuit: dict[str, Any]) -> dict[str, Any]:
    unknown_type = re.match(r"component '([^']+)' invalid type: (.+)", error)
    if unknown_type:
        component_id, component_type = unknown_type.groups()
        index = _component_index(circuit, component_id)
        return _base_item(
            code="REGISTRY_UNKNOWN_COMPONENT_TYPE",
            path=f"$.components[{index}].type" if index >= 0 else "$.components[*].type",
            message=error,
            why_it_matters="Unknown component types cannot be constrained by the registry, component cards, grammar, or verifier.",
            expected=sorted(validate.load_registry_component_types(REGISTRY_PATH)),
            actual=component_type,
            repair_hint="Replace the component type with one from verifier/config/component_registry.toml.",
            component_id=component_id,
            component_type=component_type,
            related_rule="T1-PARSE-REGISTRY",
        )

    unknown_pin = re.match(r"net '([^']+)' references unknown pin ([^ ]+) on ([A-Za-z0-9_]+)", error)
    if unknown_pin:
        net_name, pin_name, component_id = unknown_pin.groups()
        net_index, pin_index, pin_ref = _net_pin_location(circuit, net_name, component_id, pin_name)
        component_type = _component_type(circuit, component_id)
        return _base_item(
            code="PIN_UNKNOWN_FOR_COMPONENT",
            path=f"$.nets[{net_index}].pins[{pin_index}]" if net_index >= 0 and pin_index >= 0 else "$.nets[*].pins[*]",
            message=error,
            why_it_matters="A net pin reference must match a declared component pin exactly or the circuit cannot be mapped to a schematic.",
            expected=sorted(_component_pins(circuit, component_id)),
            actual=pin_name,
            repair_hint="Use one of the declared pin names on the referenced component.",
            component_id=component_id,
            component_type=component_type,
            pin_ref=pin_ref,
            net_name=net_name,
            related_component_cards=[component_type] if component_type else [],
            related_rule="T1-07",
        )

    return _base_item(
        code="SCHEMA_VALIDATION_ERROR",
        path="$",
        message=error,
        why_it_matters="The circuit must satisfy Ohmatic v0.1 structural rules before it can enter training or runtime verification.",
        expected="valid Ohmatic v0.1 circuit",
        actual=error,
        repair_hint="Correct the schema, component, pin, or net issue described in the message.",
        related_rule="T1",
    )


def _component_index(circuit: dict[str, Any], component_id: str) -> int:
    for index, component in enumerate(circuit.get("components", [])):
        if isinstance(component, dict) and component.get("id") == component_id:
            return index
    return -1


def _component_type(circuit: dict[str, Any], component_id: str) -> str:
    for component in circuit.get("components", []):
        if isinstance(component, dict) and component.get("id") == component_id:
            return str(component.get("type", ""))
    return ""


def _component_pins(circuit: dict[str, Any], component_id: str) -> set[str]:
    for component in circuit.get("components", []):
        if isinstance(component, dict) and component.get("id") == component_id and isinstance(component.get("pins"), dict):
            return set(component["pins"])
    return set()


def _net_pin_location(circuit: dict[str, Any], net_name: str, component_id: str, pin_name: str) -> tuple[int, int, str]:
    target = f"{component_id}.{pin_name}"
    for net_index, net in enumerate(circuit.get("nets", [])):
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
