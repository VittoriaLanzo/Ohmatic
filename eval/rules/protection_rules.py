"""Optocoupler, zener, and diode polarity ERC rules — T3-20 through T3-23."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from eval.diagnostic_rules import _Context

SUPPLY_POWER_TYPES = {"power_vcc", "power_3v3", "power_5v", "power_12v"}


def _net_is_supply(ctx: "_Context", net: dict) -> bool:
    """True if net is a positive supply: has power symbol type OR is a regulator output."""
    if any(ctx.component_type(cid) in SUPPLY_POWER_TYPES for cid in ctx.comps_on_net(net)):
        return True
    # Also treat ic_regulator VOUT/OUT pin as a supply
    for cid in ctx.comps_on_net(net):
        if ctx.component_type(cid) not in ("ic_regulator", "ic_power_converter"):
            continue
        comp = ctx.by_id.get(cid, {})
        pins = comp.get("pins", {})
        for pin_name, pin_net_name in pins.items():
            if pin_name in ("VOUT", "OUT") and pin_net_name == net.get("name", ""):
                return True
    return False


def protection_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    """Entry point called from diagnostic_rules.electrical_diagnostics."""
    items: list[dict[str, Any]] = []
    for rule in (
        _optocoupler_missing_current_limit,
        _zener_anode_on_high_rail,
        _diode_reversed,
        _zener_missing_series_resistor,
    ):
        items.extend(rule(ctx))
    return items


def _optocoupler_missing_current_limit(ctx: "_Context") -> list[dict[str, Any]]:
    from eval.diagnostic_rules import _net_has_resistor_to_vcc
    items = []
    for component in ctx.components:
        if component.get("type") != "optocoupler":
            continue
        component_id = str(component.get("id", ""))
        if "A" not in component.get("pins", {}):
            continue
        pin_ref = f"{component_id}.A"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        # Fire if anode is directly on a power rail (any resistor on VCC for unrelated
        # purpose must NOT satisfy this check) OR if no resistor at all on anode net.
        anode_on_power_rail = ctx.net_has_type(net, "power_vcc")
        if ctx.net_has_type(net, "resistor") and not anode_on_power_rail:
            continue
        items.append(ctx.make_item(
            code="INTERACTION_OPTOCOUPLER_INPUT_MISSING_CURRENT_LIMIT",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: optocoupler anode net '{net.get('name', '')}' has no current-limiting resistor",
            why_it_matters="The optocoupler input LED has no current limiting resistor; excessive forward current will burn out the LED and break galvanic isolation.",
            expected="a current-limiting resistor in series with the optocoupler anode (A pin)",
            actual=f"{pin_ref} on net '{net.get('name', '')}' with no resistor",
            repair_hint="Add a current-limiting resistor in series with the optocoupler anode (A pin), sized to keep IF within datasheet limits.",
            component_id=component_id,
            component_type="optocoupler",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["optocoupler", "resistor"],
            related_rule="T3-20",
        ))
    return items


def _zener_anode_on_high_rail(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "zener_diode":
            continue
        component_id = str(component.get("id", ""))
        if "A" not in component.get("pins", {}):
            continue
        pin_ref = f"{component_id}.A"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        # Anode on a supply rail → forward-biased, not performing clamping
        anode_on_supply = _net_is_supply(ctx, net)
        if not anode_on_supply:
            continue
        items.append(ctx.make_item(
            code="POLARITY_ZENER_ANODE_ON_HIGH_RAIL",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: zener_diode anode (A) is on a positive supply net '{net.get('name', '')}' — diode is forward-biased",
            why_it_matters="A zener diode with its anode on VCC is forward-biased; it acts as a standard diode rather than a voltage clamp and will draw excessive current.",
            expected="zener cathode (K) on the positive rail and anode (A) on GND or the lower rail for proper reverse-bias clamping",
            actual=f"{pin_ref} on supply net '{net.get('name', '')}'",
            repair_hint="Reverse the zener: connect cathode (K) to the positive rail and anode (A) to GND or the lower rail.",
            component_id=component_id,
            component_type="zener_diode",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["zener_diode"],
            related_rule="T3-21",
        ))
    return items


def _diode_reversed(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") not in {"diode", "schottky_diode"}:
            continue
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "A" not in pins or "K" not in pins:
            continue
        anode_ref = f"{component_id}.A"
        cathode_ref = f"{component_id}.K"
        anode_net = ctx.net_for_pin(anode_ref)
        cathode_net = ctx.net_for_pin(cathode_ref)
        if not anode_net or not cathode_net:
            continue
        # Reversed: anode on GND-like net, cathode on VCC-like net
        anode_on_gnd = (
            anode_net.get("name") == "GND"
            or ctx.net_has_type(anode_net, "power_gnd")
        )
        cathode_on_vcc = _net_is_supply(ctx, cathode_net)
        if not (anode_on_gnd and cathode_on_vcc):
            continue
        items.append(ctx.make_item(
            code="POLARITY_DIODE_REVERSED",
            path=f"$.nets[{ctx.net_index(anode_net)}].pins",
            message=f"{component_id}: {component.get('type')} anode (A) is on GND and cathode (K) is on VCC — diode is reversed",
            why_it_matters="A rectifier or protection diode installed backwards conducts in the wrong direction, clamping the supply rail or bypassing reverse-polarity protection.",
            expected="anode (A) toward the lower potential node, cathode (K) toward the higher potential node",
            actual=f"A on '{anode_net.get('name', '')}' (GND side), K on '{cathode_net.get('name', '')}' (VCC side)",
            repair_hint="Flip the diode: anode (A) toward the lower potential node, cathode (K) toward the higher potential node.",
            component_id=component_id,
            component_type=str(component.get("type", "")),
            pin_ref=anode_ref,
            net_name=str(anode_net.get("name", "")),
            related_component_cards=[str(component.get("type", ""))],
            related_rule="T3-22",
        ))
    return items


def _zener_missing_series_resistor(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "zener_diode":
            continue
        component_id = str(component.get("id", ""))
        if "K" not in component.get("pins", {}):
            continue
        pin_ref = f"{component_id}.K"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        # Only fire if cathode is directly on a supply rail.
        # When cathode IS on a supply rail, always fire: a valid series-R circuit would
        # place the zener cathode on an intermediate net (not the supply itself), so
        # any resistor elsewhere on the supply net is unrelated — it does NOT protect
        # the zener from overcurrent.
        cathode_on_supply = _net_is_supply(ctx, net)
        if not cathode_on_supply:
            continue
        items.append(ctx.make_item(
            code="INTERACTION_ZENER_CATHODE_MISSING_SERIES_RESISTOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: zener_diode cathode (K) is on a supply net '{net.get('name', '')}' with no series resistor",
            why_it_matters="A zener used as a voltage clamp must have a series resistor to limit current; direct connection to a supply will burn the zener and possibly the supply.",
            expected="a series resistor between the supply rail and the zener cathode (K)",
            actual=f"{pin_ref} on supply net '{net.get('name', '')}' with no resistor",
            repair_hint="Add a series resistor between the supply and the zener cathode (K), sized so zener current stays within Pmax.",
            component_id=component_id,
            component_type="zener_diode",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["zener_diode", "resistor"],
            related_rule="T3-23",
        ))
    return items


# ── Fixtures ──────────────────────────────────────────────────────────────────

def fixture_optocoupler_no_current_limit() -> dict[str, Any]:
    """Optocoupler anode directly on VCC with no resistor — triggers T3-20."""
    return {
        "metadata": {"title": "Bad Opto No Resistor", "description": "Optocoupler input LED driven without current limit.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "U1", "type": "optocoupler", "part": "PC817", "value": "1:1", "pins": {"A": "VCC", "K": "GND", "C": "OUT", "E": "GND"}, "x": 80, "y": 60},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "1k", "pins": {"1": "OUT", "2": "GND"}, "x": 150, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.A"]},
            {"name": "OUT", "pins": ["U1.C", "R1.1"]},
            {"name": "GND", "pins": ["GND1.1", "U1.K", "U1.E", "R1.2"]},
        ],
    }


def fixture_zener_anode_on_vcc() -> dict[str, Any]:
    """Zener anode on VCC (forward-biased) — triggers T3-21."""
    return {
        "metadata": {"title": "Bad Zener Anode On VCC", "description": "Zener diode installed forward-biased.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "1k", "pins": {"1": "VCC", "2": "ZREF"}, "x": 80, "y": 40},
            {"id": "D1", "type": "zener_diode", "part": "SOD-123", "value": "3V3", "pins": {"A": "VCC", "K": "ZREF"}, "x": 80, "y": 80},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "R1.1", "D1.A"]},
            {"name": "ZREF", "pins": ["R1.2", "D1.K"]},
            {"name": "GND", "pins": ["GND1.1"]},
        ],
    }


def fixture_diode_reversed() -> dict[str, Any]:
    """Diode installed backwards (anode on GND, cathode on VCC) — triggers T3-22."""
    return {
        "metadata": {"title": "Bad Diode Reversed", "description": "Rectifier diode installed backwards.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "D1", "type": "diode", "part": "SOD-123", "value": "1N4148", "pins": {"A": "GND", "K": "VCC"}, "x": 80, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "D1.K"]},
            {"name": "GND", "pins": ["GND1.1", "D1.A"]},
        ],
    }


def fixture_zener_cathode_direct_on_vcc() -> dict[str, Any]:
    """Zener cathode on VCC with no series resistor — triggers T3-23."""
    return {
        "metadata": {"title": "Bad Zener No Series R", "description": "Zener connected directly to VCC without series resistor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "D1", "type": "zener_diode", "part": "SOD-123", "value": "3V3", "pins": {"A": "GND", "K": "VCC"}, "x": 80, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "D1.K"]},
            {"name": "GND", "pins": ["GND1.1", "D1.A"]},
        ],
    }
