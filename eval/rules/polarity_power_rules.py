"""Polarity, rectification, and power-path ERC rules — T3-30 through T3-35."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from eval.diagnostic_rules import _Context

SUPPLY_POWER_TYPES = {"power_vcc", "power_3v3", "power_5v", "power_12v"}
RECTIFIER_TYPES = {"diode", "schottky_diode", "diode_bridge"}
PROTECTION_IC_TYPES = {"ic_protection", "ic_bms", "ic_battery_charger"}


def polarity_power_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    """Entry point called from diagnostic_rules.electrical_diagnostics."""
    items: list[dict[str, Any]] = []
    for rule in (
        _transformer_secondary_no_rectification,
        _tvs_diode_reversed,
        _battery_unprotected,
        _phototransistor_collector_reversed,
        _diode_bridge_ac_from_dc,
    ):
        items.extend(rule(ctx))
    return items


def _transformer_secondary_no_rectification(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-30: transformer secondary pins (SEC1, SEC2) with no rectifier on net."""
    items = []
    for component in ctx.components_of_type("transformer"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        secondary_pins = [p for p in pins if p.startswith("SEC")]
        if not secondary_pins:
            continue
        checked_nets: set[int] = set()
        for sec_pin in secondary_pins:
            pin_ref = f"{component_id}.{sec_pin}"
            net = ctx.net_for_pin(pin_ref)
            if not net:
                continue
            net_idx = ctx.net_index(net)
            if net_idx in checked_nets:
                continue
            checked_nets.add(net_idx)
            # Check all nets connected to the secondary winding for a rectifier
            peers = ctx.comps_on_net(net) - {component_id}
            has_rectifier = any(ctx.component_type(cid) in RECTIFIER_TYPES for cid in peers)
            if has_rectifier:
                continue
            items.append(ctx.make_item(
                code="POWER_TRANSFORMER_SECONDARY_MISSING_RECTIFIER",
                path=f"$.nets[{net_idx}].pins",
                message=f"{component_id}: transformer secondary net '{net.get('name', '')}' has no rectifier diode or bridge",
                why_it_matters="AC from the transformer secondary must be rectified before being used as DC; without rectification, connected ICs and capacitors receive AC voltage and will be damaged.",
                expected="a diode, schottky_diode, or diode_bridge on the transformer secondary net",
                actual=f"{pin_ref} on '{net.get('name', '')}' with no rectifier",
                repair_hint="Add a rectifier diode (or diode bridge for full-wave) between the transformer secondary and the DC bus capacitor.",
                component_id=component_id,
                component_type="transformer",
                pin_ref=pin_ref,
                net_name=str(net.get("name", "")),
                related_component_cards=["transformer", "diode", "diode_bridge"],
                related_rule="T3-30",
            ))
    return items


def _tvs_diode_reversed(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-32: tvs_diode anode on a positive supply rail — forward biased, not clamping."""
    items = []
    for component in ctx.components_of_type("tvs_diode"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "A" not in pins or "K" not in pins:
            continue
        anode_ref = f"{component_id}.A"
        anode_net = ctx.net_for_pin(anode_ref)
        if not anode_net:
            continue
        anode_on_supply = (
            anode_net.get("name") == "VCC"
            or any(ctx.component_type(cid) in SUPPLY_POWER_TYPES for cid in ctx.comps_on_net(anode_net))
        )
        if not anode_on_supply:
            continue
        items.append(ctx.make_item(
            code="POLARITY_TVS_DIODE_REVERSED",
            path=f"$.nets[{ctx.net_index(anode_net)}].pins",
            message=f"{component_id}: tvs_diode anode (A) is on supply net '{anode_net.get('name', '')}' — TVS is forward-biased, not clamping",
            why_it_matters="A TVS diode with its anode on the positive rail is forward biased; it clamps the line to ~0.7 V above GND, not the intended reverse-breakdown clamp voltage.",
            expected="tvs_diode cathode (K) toward the positive rail and anode (A) toward GND or the protected node for proper transient clamping",
            actual=f"{anode_ref} on supply net '{anode_net.get('name', '')}'",
            repair_hint="Reverse the TVS: cathode (K) to the positive rail or protected node, anode (A) to GND.",
            component_id=component_id,
            component_type="tvs_diode",
            pin_ref=anode_ref,
            net_name=str(anode_net.get("name", "")),
            related_component_cards=["tvs_diode"],
            related_rule="T3-32",
        ))
    return items


def _battery_unprotected(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-33: battery with no protection IC, fuse, or polyfuse on its output net."""
    FUSE_TYPES = {"fuse", "polyfuse", "ferrite_bead"}
    items = []
    for component in ctx.components_of_type("battery"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        # Look for the positive terminal — usually pin "+" or "1"
        pos_pin = next((p for p in ("+", "1", "POS", "VBAT") if p in pins), None)
        if not pos_pin:
            continue
        pin_ref = f"{component_id}.{pos_pin}"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        peers = ctx.comps_on_net(net) - {component_id}
        has_protection = any(
            ctx.component_type(cid) in (PROTECTION_IC_TYPES | FUSE_TYPES)
            for cid in peers
        )
        if has_protection:
            continue
        items.append(ctx.make_item(
            code="POWER_BATTERY_MISSING_PROTECTION",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: battery positive terminal net '{net.get('name', '')}' has no protection IC or fuse",
            why_it_matters="An unprotected lithium battery can be over-discharged, over-charged, or short-circuited, leading to fire, swelling, or explosion.",
            expected="a battery protection IC, BMS, charger IC, or at minimum a fuse/polyfuse on the battery output path",
            actual=f"{pin_ref} on '{net.get('name', '')}' with no protection element",
            repair_hint="Add a battery protection IC or BMS (e.g., DW01A + FS8205) on the battery output, or at minimum a polyfuse for overcurrent protection.",
            component_id=component_id,
            component_type="battery",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["battery", "ic_bms", "ic_battery_charger", "fuse"],
            related_rule="T3-33",
        ))
    return items


def _phototransistor_collector_reversed(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-34: phototransistor collector (C) on GND and emitter (E) on VCC — reversed biasing."""
    items = []
    for component in ctx.components_of_type("phototransistor"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "C" not in pins or "E" not in pins:
            continue
        collector_ref = f"{component_id}.C"
        emitter_ref = f"{component_id}.E"
        collector_net = ctx.net_for_pin(collector_ref)
        emitter_net = ctx.net_for_pin(emitter_ref)
        if not collector_net or not emitter_net:
            continue
        collector_on_gnd = (
            collector_net.get("name") == "GND"
            or ctx.net_has_type(collector_net, "power_gnd")
        )
        emitter_on_vcc = (
            emitter_net.get("name") == "VCC"
            or any(ctx.component_type(cid) in SUPPLY_POWER_TYPES for cid in ctx.comps_on_net(emitter_net))
        )
        if not (collector_on_gnd and emitter_on_vcc):
            continue
        items.append(ctx.make_item(
            code="POLARITY_PHOTOTRANSISTOR_REVERSED",
            path=f"$.nets[{ctx.net_index(collector_net)}].pins",
            message=f"{component_id}: phototransistor collector (C) is on GND and emitter (E) is on VCC — transistor is reversed",
            why_it_matters="A phototransistor biased with emitter at VCC and collector at GND operates in reverse active mode; it will not respond correctly to light and output characteristics are unreliable.",
            expected="collector (C) toward the positive rail, emitter (E) toward GND for standard common-emitter operation",
            actual=f"C on GND '{collector_net.get('name', '')}', E on VCC '{emitter_net.get('name', '')}'",
            repair_hint="Flip the phototransistor: connect collector (C) to the pull-up resistor toward VCC and emitter (E) to GND.",
            component_id=component_id,
            component_type="phototransistor",
            pin_ref=collector_ref,
            net_name=str(collector_net.get("name", "")),
            related_component_cards=["phototransistor"],
            related_rule="T3-34",
        ))
    return items


def _diode_bridge_ac_from_dc(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-35: diode_bridge AC input pins fed from a DC supply rail."""
    items = []
    for component in ctx.components_of_type("diode_bridge"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        for ac_pin in ("AC1", "AC2", "~1", "~2"):
            if ac_pin not in pins:
                continue
            pin_ref = f"{component_id}.{ac_pin}"
            net = ctx.net_for_pin(pin_ref)
            if not net:
                continue
            # If a DC supply type is directly on this AC input net, flag it
            peers = ctx.comps_on_net(net) - {component_id}
            ac_fed_from_dc = any(ctx.component_type(cid) in SUPPLY_POWER_TYPES for cid in peers)
            if not ac_fed_from_dc:
                continue
            items.append(ctx.make_item(
                code="INTERACTION_DIODE_BRIDGE_AC_FROM_DC_RAIL",
                path=f"$.nets[{ctx.net_index(net)}].pins",
                message=f"{component_id}: diode_bridge AC input pin '{ac_pin}' is connected to a DC supply net '{net.get('name', '')}'",
                why_it_matters="A diode bridge rectifier expects AC on its input pins; connecting a DC rail to the AC inputs wastes power, creates unexpected current paths, and defeats the rectification purpose.",
                expected="AC source (e.g., transformer secondary) on diode_bridge AC1/AC2 pins, not a DC power rail",
                actual=f"{pin_ref} on DC supply net '{net.get('name', '')}'",
                repair_hint="Feed the diode bridge AC input pins from a transformer secondary or AC source, not from a DC power rail.",
                component_id=component_id,
                component_type="diode_bridge",
                pin_ref=pin_ref,
                net_name=str(net.get("name", "")),
                related_component_cards=["diode_bridge", "transformer"],
                related_rule="T3-35",
            ))
    return items


# ── Fixtures ──────────────────────────────────────────────────────────────────

def fixture_transformer_no_rectifier() -> dict[str, Any]:
    """Transformer secondary with no rectifier — triggers T3-30."""
    return {
        "metadata": {"title": "Bad Transformer No Rectifier", "description": "Transformer secondary directly connected to DC bus without rectification.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "T1", "type": "transformer", "part": "EI30", "value": "12VAC", "pins": {"PRI1": "MAINS_L", "PRI2": "MAINS_N", "SEC1": "AC_OUT1", "SEC2": "AC_OUT2"}, "x": 80, "y": 60},
            {"id": "C1", "type": "capacitor", "part": "2200uF", "value": "2200uF", "pins": {"1": "AC_OUT1", "2": "AC_OUT2"}, "x": 180, "y": 60},
        ],
        "nets": [
            {"name": "MAINS_L", "pins": ["T1.PRI1"]},
            {"name": "MAINS_N", "pins": ["T1.PRI2"]},
            {"name": "AC_OUT1", "pins": ["T1.SEC1", "C1.1"]},
            {"name": "AC_OUT2", "pins": ["T1.SEC2", "C1.2"]},
        ],
    }


def fixture_tvs_reversed() -> dict[str, Any]:
    """TVS diode with anode on VCC (forward biased) — triggers T3-32."""
    return {
        "metadata": {"title": "Bad TVS Reversed", "description": "TVS diode installed forwards on supply rail.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "D1", "type": "tvs_diode", "part": "SMF5V0A", "value": "5V TVS", "pins": {"A": "VCC", "K": "GND"}, "x": 80, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "D1.A"]},
            {"name": "GND", "pins": ["GND1.1", "D1.K"]},
        ],
    }


def fixture_battery_unprotected() -> dict[str, Any]:
    """Battery with no BMS or fuse — triggers T3-33."""
    return {
        "metadata": {"title": "Bad Battery Unprotected", "description": "Lithium battery with no protection circuit.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "BT1", "type": "battery", "part": "18650", "value": "3.7V LiPo", "pins": {"+": "VBAT", "-": "GND"}, "x": 0, "y": 60},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 160},
            {"id": "U1", "type": "ic_mcu", "part": "STM32", "value": "STM32L4", "pins": {"VCC": "VBAT", "GND": "GND"}, "x": 120, "y": 60},
        ],
        "nets": [
            {"name": "VBAT", "pins": ["BT1.+", "U1.VCC"]},
            {"name": "GND", "pins": ["GND1.1", "BT1.-", "U1.GND"]},
        ],
    }


def fixture_diode_bridge_ac_from_dc() -> dict[str, Any]:
    """Diode bridge AC input fed from DC rail — triggers T3-35."""
    return {
        "metadata": {"title": "Bad Bridge AC From DC", "description": "Diode bridge AC pins connected to DC supply.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "12V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 160},
            {"id": "D1", "type": "diode_bridge", "part": "KBP206", "value": "600V 2A", "pins": {"AC1": "VCC", "AC2": "GND", "+": "DC_POS", "-": "DC_NEG"}, "x": 100, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "D1.AC1"]},
            {"name": "GND", "pins": ["GND1.1", "D1.AC2"]},
            {"name": "DC_POS", "pins": ["D1.+"]},
            {"name": "DC_NEG", "pins": ["D1.-"]},
        ],
    }
