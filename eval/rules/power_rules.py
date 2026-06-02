"""Power regulation and oscillator ERC rules — T3-09 through T3-12."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from eval.diagnostic_rules import _Context


def _net_has_cap_to_gnd(ctx, net):  # type: ignore[no-untyped-def]
    """Lazy proxy — defers import of _net_has_cap_to_gnd to avoid circular import."""
    import eval.diagnostic_rules as _dr  # noqa: PLC0415
    return _dr._net_has_cap_to_gnd(ctx, net)


def power_regulation_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    """Entry point called from diagnostic_rules.electrical_diagnostics."""
    items: list[dict[str, Any]] = []
    for rule in (
        _regulator_missing_output_cap,
        _regulator_missing_input_cap,
        _crystal_missing_load_caps,
        _converter_missing_output_cap,
    ):
        items.extend(rule(ctx))
    return items


def _regulator_missing_output_cap(ctx: "_Context") -> list[dict[str, Any]]:
    from eval.diagnostic_rules import _net_has_cap_to_gnd  # lazy import to break circular dependency
    items = []
    for component in ctx.components:
        if component.get("type") != "ic_regulator":
            continue
        comp_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        out_pin = next((p for p in ("VOUT", "OUT") if p in pins), None)
        if not out_pin:
            continue
        pin_ref = f"{comp_id}.{out_pin}"
        net = ctx.net_for_pin(pin_ref)
        if not net or _net_has_cap_to_gnd(ctx, net):
            continue
        items.append(ctx.make_item(
            code="POWER_REGULATOR_MISSING_OUTPUT_CAPACITOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{comp_id}: ic_regulator VOUT net '{net.get('name', '')}' has no output capacitor",
            why_it_matters="Linear regulators require an output capacitor for loop stability; without it the regulator can oscillate and destroy downstream ICs.",
            expected="at least one capacitor on the VOUT net between output and GND",
            actual=f"{pin_ref} on net '{net.get('name', '')}' with no capacitor",
            repair_hint="Add a capacitor from VOUT to GND (typically 10µF ceramic or electrolytic).",
            component_id=comp_id,
            component_type="ic_regulator",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["ic_regulator", "capacitor"],
            related_rule="T3-09",
            severity="error",
        ))
    return items


def _regulator_missing_input_cap(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "ic_regulator":
            continue
        comp_id = str(component.get("id", ""))
        if "VIN" not in component.get("pins", {}):
            continue
        pin_ref = f"{comp_id}.VIN"
        net = ctx.net_for_pin(pin_ref)
        if not net or _net_has_cap_to_gnd(ctx, net):
            continue
        items.append(ctx.make_item(
            code="POWER_REGULATOR_MISSING_INPUT_CAPACITOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{comp_id}: ic_regulator VIN net '{net.get('name', '')}' has no input capacitor",
            why_it_matters="Input capacitors absorb supply transients and prevent regulator dropout oscillation under load steps.",
            expected="at least one capacitor on the VIN net",
            actual=f"{pin_ref} on net '{net.get('name', '')}' with no capacitor",
            repair_hint="Add a capacitor from VIN to GND (typically 100nF ceramic).",
            component_id=comp_id,
            component_type="ic_regulator",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["ic_regulator", "capacitor"],
            related_rule="T3-10",
            severity="warning",
        ))
    return items


def _crystal_missing_load_caps(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "crystal":
            continue
        comp_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        for osc_pin in ("1", "2"):
            if osc_pin not in pins:
                continue
            pin_ref = f"{comp_id}.{osc_pin}"
            net = ctx.net_for_pin(pin_ref)
            if not net or _net_has_cap_to_gnd(ctx, net):
                continue
            items.append(ctx.make_item(
                code="POWER_CRYSTAL_MISSING_LOAD_CAPACITOR",
                path=f"$.nets[{ctx.net_index(net)}].pins",
                message=f"{comp_id}: crystal pin {osc_pin} on net '{net.get('name', '')}' has no load capacitor",
                why_it_matters="Crystal oscillators require load capacitors on both oscillator pins to start reliably and reach the rated frequency.",
                expected=f"a capacitor from crystal pin {osc_pin} to GND (typically 18–22pF)",
                actual=f"{pin_ref} on net '{net.get('name', '')}' with no capacitor",
                repair_hint="Add a load capacitor (typically 18–22pF) from each crystal pin to GND.",
                component_id=comp_id,
                component_type="crystal",
                pin_ref=pin_ref,
                net_name=str(net.get("name", "")),
                related_component_cards=["crystal", "capacitor"],
                related_rule="T3-11",
                severity="error",
            ))
    return items


def _converter_missing_output_cap(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "ic_power_converter":
            continue
        comp_id = str(component.get("id", ""))
        if "VOUT" not in component.get("pins", {}):
            continue
        pin_ref = f"{comp_id}.VOUT"
        net = ctx.net_for_pin(pin_ref)
        if not net or _net_has_cap_to_gnd(ctx, net):
            continue
        items.append(ctx.make_item(
            code="POWER_CONVERTER_MISSING_OUTPUT_CAPACITOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{comp_id}: ic_power_converter VOUT net '{net.get('name', '')}' has no output capacitor",
            why_it_matters="DC-DC converters require output capacitors for ripple filtering and stability of the control loop.",
            expected="at least one capacitor on the VOUT net (bulk electrolytic + ceramic as per datasheet)",
            actual=f"{pin_ref} on net '{net.get('name', '')}' with no capacitor",
            repair_hint="Add output capacitors as specified in the converter datasheet (typically bulk electrolytic + ceramic).",
            component_id=comp_id,
            component_type="ic_power_converter",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["ic_power_converter", "capacitor"],
            related_rule="T3-12",
            severity="error",
        ))
    return items


# ── Fixtures ──────────────────────────────────────────────────────────────────

def fixture_regulator_missing_output_cap() -> dict[str, Any]:
    """ic_regulator VOUT with no capacitor → triggers T3-09."""
    return {
        "metadata": {"title": "Bad Reg No Output Cap", "description": "LDO with no output cap.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "12V", "pins": {"1": "VIN_RAIL"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 100},
            {"id": "U1", "type": "ic_regulator", "part": "SOT-223", "value": "5V", "pins": {"VIN": "VIN_RAIL", "VOUT": "VOUT_RAIL", "GND": "GND"}, "x": 80, "y": 50},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "100", "pins": {"1": "VOUT_RAIL", "2": "GND"}, "x": 140, "y": 50},
        ],
        "nets": [
            {"name": "VIN_RAIL", "pins": ["VCC1.1", "U1.VIN"]},
            {"name": "VOUT_RAIL", "pins": ["U1.VOUT", "R1.1"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "R1.2"]},
        ],
    }


def fixture_regulator_missing_input_cap() -> dict[str, Any]:
    """ic_regulator VIN with no capacitor → triggers T3-10."""
    return {
        "metadata": {"title": "Bad Reg No Input Cap", "description": "LDO with no input cap.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "12V", "pins": {"1": "VIN_RAIL"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 100},
            {"id": "U1", "type": "ic_regulator", "part": "SOT-223", "value": "5V", "pins": {"VIN": "VIN_RAIL", "VOUT": "VOUT_RAIL", "GND": "GND"}, "x": 80, "y": 50},
            {"id": "C1", "type": "capacitor", "part": "0805", "value": "10uF", "pins": {"1": "VOUT_RAIL", "2": "GND"}, "x": 140, "y": 50},
        ],
        "nets": [
            {"name": "VIN_RAIL", "pins": ["VCC1.1", "U1.VIN"]},
            {"name": "VOUT_RAIL", "pins": ["U1.VOUT", "C1.1"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "C1.2"]},
        ],
    }


def fixture_crystal_missing_load_caps() -> dict[str, Any]:
    """Crystal with no load capacitors → triggers T3-11 (both pins)."""
    return {
        "metadata": {"title": "Bad Crystal No Load Caps", "description": "Crystal with no load caps.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "3V3", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "Y1", "type": "crystal", "part": "HC-49S", "value": "16MHz", "pins": {"1": "XTAL1", "2": "XTAL2"}, "x": 80, "y": 60},
            {"id": "U1", "type": "ic_mcu", "part": "QFP-32", "value": "ATmega328", "pins": {"VCC": "VCC", "GND": "GND", "XTAL1": "XTAL1", "XTAL2": "XTAL2"}, "x": 160, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND"]},
            {"name": "XTAL1", "pins": ["Y1.1", "U1.XTAL1"]},
            {"name": "XTAL2", "pins": ["Y1.2", "U1.XTAL2"]},
        ],
    }


def fixture_converter_missing_output_cap() -> dict[str, Any]:
    """ic_power_converter VOUT with no capacitor → triggers T3-12."""
    return {
        "metadata": {"title": "Bad Buck No Output Cap", "description": "Buck converter with no output cap.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "12V", "pins": {"1": "VIN_RAIL"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 100},
            {"id": "U1", "type": "ic_power_converter", "part": "SOT-23-5", "value": "5V/1A", "pins": {"VIN": "VIN_RAIL", "VOUT": "VOUT_RAIL", "GND": "GND", "FB": "FB_NODE", "EN": "VIN_RAIL"}, "x": 80, "y": 50},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "100k", "pins": {"1": "VOUT_RAIL", "2": "FB_NODE"}, "x": 140, "y": 40},
            {"id": "R2", "type": "resistor", "part": "0603", "value": "10k", "pins": {"1": "FB_NODE", "2": "GND"}, "x": 140, "y": 70},
        ],
        "nets": [
            {"name": "VIN_RAIL", "pins": ["VCC1.1", "U1.VIN", "U1.EN"]},
            {"name": "VOUT_RAIL", "pins": ["U1.VOUT", "R1.1"]},
            {"name": "FB_NODE", "pins": ["U1.FB", "R1.2", "R2.1"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "R2.2"]},
        ],
    }
