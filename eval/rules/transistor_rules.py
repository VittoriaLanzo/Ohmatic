"""Transistor, IGBT, SCR, and TRIAC gate/base ERC rules - T3-13 through T3-16."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from eval.diagnostic_rules import _Context

GATE_DRIVER_TYPES = {"resistor", "power_vcc", "power_gnd", "ic_driver", "ic_logic", "ic_mcu", "connector"}


def transistor_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    """Entry point called from diagnostic_rules.electrical_diagnostics."""
    items: list[dict[str, Any]] = []
    for rule in (
        _bjt_base_missing_resistor,
        _igbt_gate_missing_driver,
        _scr_gate_missing_resistor,
        _triac_gate_missing_resistor,
    ):
        items.extend(rule(ctx))
    return items


def _bjt_base_missing_resistor(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") not in {"transistor_npn", "transistor_pnp"}:
            continue
        component_id = str(component.get("id", ""))
        if "B" not in component.get("pins", {}):
            continue
        pin_ref = f"{component_id}.B"
        net = ctx.net_for_pin(pin_ref)
        if not net or ctx.net_has_type(net, "resistor"):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_BJT_BASE_MISSING_RESISTOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: BJT base net '{net.get('name', '')}' has no current-limiting resistor",
            why_it_matters="A BJT base driven directly from a logic output without a series resistor can draw excessive base current and damage the driving IC or the transistor.",
            expected="a resistor in series between the driver and the BJT base",
            actual=f"{pin_ref} on {net.get('name', '')}",
            repair_hint="Insert a base resistor (typically 1k-10kΩ) in series between the driver and the BJT base.",
            component_id=component_id,
            component_type=str(component.get("type", "")),
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=[str(component.get("type", "")), "resistor"],
            related_rule="T3-13",
        ))
    return items


def _igbt_gate_missing_driver(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "igbt":
            continue
        component_id = str(component.get("id", ""))
        if "G" not in component.get("pins", {}):
            continue
        pin_ref = f"{component_id}.G"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        peer_ids = ctx.comps_on_net(net) - {component_id}
        has_driver = any(ctx.component_type(pid) in GATE_DRIVER_TYPES for pid in peer_ids)
        if has_driver:
            continue
        items.append(ctx.make_item(
            code="INTERACTION_IGBT_GATE_MISSING_DRIVER",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: IGBT gate on net '{net.get('name', '')}' has no driver or bias component",
            why_it_matters="An IGBT gate without a driver or bias resistor can turn on unpredictably from noise, leading to shoot-through or load damage.",
            expected="gate net includes a resistor, driver, logic IC, MCU, connector, VCC, or GND bias source",
            actual=f"{pin_ref} on {net.get('name', '')}",
            repair_hint="Add a gate resistor and/or dedicated IGBT gate driver IC.",
            component_id=component_id,
            component_type="igbt",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["igbt", "resistor", "ic_driver"],
            related_rule="T3-14",
        ))
    return items


def _scr_gate_missing_resistor(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "thyristor_scr":
            continue
        component_id = str(component.get("id", ""))
        if "G" not in component.get("pins", {}):
            continue
        pin_ref = f"{component_id}.G"
        net = ctx.net_for_pin(pin_ref)
        if not net or ctx.net_has_type(net, "resistor"):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_SCR_GATE_MISSING_RESISTOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: SCR gate net '{net.get('name', '')}' has no current-limiting resistor",
            why_it_matters="An SCR gate without a resistor is susceptible to noise-triggered false firing and has no current limit, which can damage the gate junction.",
            expected="a resistor in series on the SCR gate net",
            actual=f"{pin_ref} on {net.get('name', '')}",
            repair_hint="Add a series gate resistor (typically 47Ω-1kΩ) and optionally a pull-down to cathode.",
            component_id=component_id,
            component_type="thyristor_scr",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["thyristor_scr", "resistor"],
            related_rule="T3-15",
        ))
    return items


def _triac_gate_missing_resistor(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "triac":
            continue
        component_id = str(component.get("id", ""))
        if "G" not in component.get("pins", {}):
            continue
        pin_ref = f"{component_id}.G"
        net = ctx.net_for_pin(pin_ref)
        if not net or ctx.net_has_type(net, "resistor"):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_TRIAC_GATE_MISSING_RESISTOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: TRIAC gate net '{net.get('name', '')}' has no current-limiting resistor",
            why_it_matters="A TRIAC gate without a series resistor can be noise-triggered or have unlimited gate surge current.",
            expected="a resistor in series on the TRIAC gate net",
            actual=f"{pin_ref} on {net.get('name', '')}",
            repair_hint="Add a series gate resistor (typically 100Ω-1kΩ).",
            component_id=component_id,
            component_type="triac",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["triac", "resistor"],
            related_rule="T3-16",
        ))
    return items


# ── Fixtures ──────────────────────────────────────────────────────────────────

def fixture_bjt_base_no_resistor() -> dict[str, Any]:
    """NPN with base driven directly from MCU - triggers T3-13."""
    return {
        "metadata": {"title": "Bad BJT Base No Resistor", "description": "NPN base driven directly from MCU output with no series resistor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "U1", "type": "ic_mcu", "part": "QFP", "value": "MCU", "pins": {"VCC": "VCC", "GND": "GND", "PA0": "BASE_DRIVE"}, "x": 60, "y": 40},
            {"id": "Q1", "type": "transistor_npn", "part": "SOT-23", "value": "NPN", "pins": {"B": "BASE_DRIVE", "C": "VCC", "E": "GND"}, "x": 160, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC", "Q1.C"]},
            {"name": "BASE_DRIVE", "pins": ["U1.PA0", "Q1.B"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "Q1.E"]},
        ],
    }


def fixture_igbt_gate_no_driver() -> dict[str, Any]:
    """IGBT with gate connected only to a capacitor - triggers T3-14."""
    return {
        "metadata": {"title": "Bad IGBT Gate No Driver", "description": "IGBT gate on a net with only a capacitor - no driver or bias.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "15V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 140},
            {"id": "Q1", "type": "igbt", "part": "TO-247", "value": "IGBT", "pins": {"G": "GATE", "C": "VCC", "E": "GND"}, "x": 100, "y": 70},
            {"id": "C1", "type": "capacitor", "part": "0603", "value": "10nF", "pins": {"1": "GATE", "2": "GND"}, "x": 160, "y": 90},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "Q1.C"]},
            {"name": "GATE", "pins": ["Q1.G", "C1.1"]},
            {"name": "GND", "pins": ["GND1.1", "Q1.E", "C1.2"]},
        ],
    }


def fixture_scr_gate_no_resistor() -> dict[str, Any]:
    """SCR with gate driven directly from logic - triggers T3-15."""
    return {
        "metadata": {"title": "Bad SCR Gate No Resistor", "description": "SCR gate connected directly to MCU output with no series resistor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 140},
            {"id": "U1", "type": "ic_mcu", "part": "QFP", "value": "MCU", "pins": {"VCC": "VCC", "GND": "GND", "PA0": "SCR_GATE"}, "x": 60, "y": 40},
            {"id": "SCR1", "type": "thyristor_scr", "part": "TO-92", "value": "SCR", "pins": {"A": "VCC", "K": "GND", "G": "SCR_GATE"}, "x": 170, "y": 70},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC", "SCR1.A"]},
            {"name": "SCR_GATE", "pins": ["U1.PA0", "SCR1.G"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "SCR1.K"]},
        ],
    }


def fixture_triac_gate_no_resistor() -> dict[str, Any]:
    """TRIAC with gate driven directly from logic - triggers T3-16."""
    return {
        "metadata": {"title": "Bad TRIAC Gate No Resistor", "description": "TRIAC gate connected directly to MCU output with no series resistor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 140},
            {"id": "U1", "type": "ic_mcu", "part": "QFP", "value": "MCU", "pins": {"VCC": "VCC", "GND": "GND", "PA0": "TRIAC_GATE"}, "x": 60, "y": 40},
            {"id": "TR1", "type": "triac", "part": "TO-92", "value": "TRIAC", "pins": {"MT1": "GND", "MT2": "VCC", "G": "TRIAC_GATE"}, "x": 170, "y": 70},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC", "TR1.MT2"]},
            {"name": "TRIAC_GATE", "pins": ["U1.PA0", "TR1.G"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "TR1.MT1"]},
        ],
    }
