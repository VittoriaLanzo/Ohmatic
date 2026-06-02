"""Inductive load and speaker drive ERC rules — T3-17 through T3-19."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from eval.diagnostic_rules import _Context

FLYBACK_DIODE_TYPES = {"diode", "schottky_diode", "tvs_diode"}
SPEAKER_DRIVER_TYPES = {"ic_audio_amp", "ic_driver", "transistor_npn", "transistor_pnp", "mosfet_n", "mosfet_p"}


def inductive_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    """Entry point called from diagnostic_rules.electrical_diagnostics."""
    items: list[dict[str, Any]] = []
    for rule in (
        _relay_missing_flyback,
        _relay_flyback_diode_reversed,
        _motor_dc_missing_flyback,
        _motor_flyback_diode_reversed,
        _speaker_direct_mcu_drive,
    ):
        items.extend(rule(ctx))
    return items


def _relay_missing_flyback(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "relay":
            continue
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "A1" not in pins:
            continue
        # Collect all component IDs on either coil net
        coil_comp_ids: set[str] = set()
        for coil_pin in ("A1", "A2"):
            if coil_pin not in pins:
                continue
            pin_ref = f"{component_id}.{coil_pin}"
            net = ctx.net_for_pin(pin_ref)
            if net:
                coil_comp_ids |= ctx.comps_on_net(net)
        coil_comp_ids.discard(component_id)
        has_flyback = any(ctx.component_type(cid) in FLYBACK_DIODE_TYPES for cid in coil_comp_ids)
        if has_flyback:
            continue
        pin_ref = f"{component_id}.A1"
        net = ctx.net_for_pin(pin_ref)
        items.append(ctx.make_item(
            code="INTERACTION_RELAY_COIL_MISSING_FLYBACK_DIODE",
            path=f"$.nets[{ctx.net_index(net)}].pins" if net else "$.components",
            message=f"{component_id}: relay coil has no flyback diode across pins A1/A2",
            why_it_matters="Relay coils are inductive; when de-energized they produce a back-EMF spike that can destroy the driving transistor or damage nearby ICs.",
            expected="a flyback diode (diode, schottky_diode, or tvs_diode) connected across the relay coil pins A1/A2",
            actual=f"{component_id} coil with no flyback diode on A1 or A2 nets",
            repair_hint="Place a flyback diode across the relay coil pins A1/A2, cathode toward the positive rail.",
            component_id=component_id,
            component_type="relay",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")) if net else "",
            related_component_cards=["relay", "diode", "schottky_diode"],
            related_rule="T3-17",
        ))
    return items


def _relay_flyback_diode_reversed(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-17 polarity: flyback diode exists but is reversed (anode toward supply)."""
    items = []
    for component in ctx.components:
        if component.get("type") != "relay":
            continue
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "A1" not in pins:
            continue
        # Collect nets for coil pins and all diodes on those nets
        coil_nets = []
        for coil_pin in ("A1", "A2"):
            if coil_pin not in pins:
                continue
            net = ctx.net_for_pin(f"{component_id}.{coil_pin}")
            if net:
                coil_nets.append(net)
        coil_comp_ids: set[str] = set()
        for net in coil_nets:
            coil_comp_ids |= ctx.comps_on_net(net)
        coil_comp_ids.discard(component_id)
        for cid in coil_comp_ids:
            if ctx.component_type(cid) not in FLYBACK_DIODE_TYPES:
                continue
            comp = ctx.by_id.get(cid, {})
            anode_net = ctx.net_for_pin(f"{cid}.A")
            if anode_net and ctx.net_has_type(anode_net, "power_vcc"):
                # Anode on supply side → reversed
                items.append(ctx.make_item(
                    code="INTERACTION_RELAY_FLYBACK_DIODE_REVERSED",
                    path=f"$.nets[{ctx.net_index(anode_net)}].pins",
                    message=f"{cid}: flyback diode anode (A) is on the supply side of relay {component_id} — diode is reversed",
                    why_it_matters="A reversed flyback diode conducts continuously when the switch is ON, shorting the supply through the driver and destroying it.",
                    expected="cathode (K) toward the positive rail, anode (A) toward the switching node",
                    actual=f"{cid}.A on supply net '{anode_net.get('name', '')}'",
                    repair_hint="Flip the flyback diode: cathode (K) to the positive rail (A1), anode (A) to the switching node (A2).",
                    component_id=cid,
                    component_type=str(comp.get("type", "")),
                    pin_ref=f"{cid}.A",
                    net_name=str(anode_net.get("name", "")),
                    related_component_cards=["relay", "diode", "schottky_diode"],
                    related_rule="T3-17",
                ))
    return items


def _motor_dc_missing_flyback(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "motor_dc":
            continue
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        # Collect component IDs on both motor terminal nets
        motor_comp_ids: set[str] = set()
        first_net = None
        for terminal in ("1", "2"):
            if terminal not in pins:
                continue
            pin_ref = f"{component_id}.{terminal}"
            net = ctx.net_for_pin(pin_ref)
            if net:
                if first_net is None:
                    first_net = net
                motor_comp_ids |= ctx.comps_on_net(net)
        motor_comp_ids.discard(component_id)
        has_flyback = any(ctx.component_type(cid) in FLYBACK_DIODE_TYPES for cid in motor_comp_ids)
        if has_flyback:
            continue
        items.append(ctx.make_item(
            code="INTERACTION_MOTOR_DC_MISSING_FLYBACK_DIODE",
            path=f"$.nets[{ctx.net_index(first_net)}].pins" if first_net else "$.components",
            message=f"{component_id}: DC motor has no flyback diode across its terminals",
            why_it_matters="DC motors are inductive; switching them without flyback protection generates voltage spikes that can latch up or destroy H-bridge or driver ICs.",
            expected="flyback diodes (diode, schottky_diode, or tvs_diode) across the motor terminals",
            actual=f"{component_id} with no flyback diode on terminal nets",
            repair_hint="Add flyback diodes across the motor terminals, or use an H-bridge IC with integrated protection diodes.",
            component_id=component_id,
            component_type="motor_dc",
            pin_ref=f"{component_id}.1",
            net_name=str(first_net.get("name", "")) if first_net else "",
            related_component_cards=["motor_dc", "diode", "schottky_diode", "ic_driver"],
            related_rule="T3-18",
        ))
    return items


def _motor_flyback_diode_reversed(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-18 polarity: flyback diode exists but is reversed (anode toward supply)."""
    items = []
    for component in ctx.components:
        if component.get("type") != "motor_dc":
            continue
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        motor_nets = []
        for terminal in ("1", "2"):
            if terminal not in pins:
                continue
            net = ctx.net_for_pin(f"{component_id}.{terminal}")
            if net:
                motor_nets.append(net)
        motor_comp_ids: set[str] = set()
        for net in motor_nets:
            motor_comp_ids |= ctx.comps_on_net(net)
        motor_comp_ids.discard(component_id)
        for cid in motor_comp_ids:
            if ctx.component_type(cid) not in FLYBACK_DIODE_TYPES:
                continue
            comp = ctx.by_id.get(cid, {})
            anode_net = ctx.net_for_pin(f"{cid}.A")
            if anode_net and ctx.net_has_type(anode_net, "power_vcc"):
                # Anode on supply side → reversed
                items.append(ctx.make_item(
                    code="INTERACTION_MOTOR_FLYBACK_DIODE_REVERSED",
                    path=f"$.nets[{ctx.net_index(anode_net)}].pins",
                    message=f"{cid}: flyback diode anode (A) is on the supply side of motor {component_id} — diode is reversed",
                    why_it_matters="A reversed flyback diode conducts continuously when the switch is ON, shorting the supply through the driver and destroying it.",
                    expected="cathode (K) toward the positive rail, anode (A) toward the switching node",
                    actual=f"{cid}.A on supply net '{anode_net.get('name', '')}'",
                    repair_hint="Flip the flyback diode: cathode (K) to the positive rail, anode (A) to the switching node.",
                    component_id=cid,
                    component_type=str(comp.get("type", "")),
                    pin_ref=f"{cid}.A",
                    net_name=str(anode_net.get("name", "")),
                    related_component_cards=["motor_dc", "diode", "schottky_diode"],
                    related_rule="T3-18",
                ))
    return items


def _speaker_direct_mcu_drive(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components:
        if component.get("type") != "speaker":
            continue
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        # Collect all component types on speaker terminal nets
        speaker_comp_ids: set[str] = set()
        first_net = None
        for terminal in ("1", "2"):
            if terminal not in pins:
                continue
            pin_ref = f"{component_id}.{terminal}"
            net = ctx.net_for_pin(pin_ref)
            if net:
                if first_net is None:
                    first_net = net
                speaker_comp_ids |= ctx.comps_on_net(net)
        speaker_comp_ids.discard(component_id)
        peer_types = {ctx.component_type(cid) for cid in speaker_comp_ids}
        # Only fire if MCU or logic IC is directly connected and no driver type is present
        if not peer_types & {"ic_mcu", "ic_logic"}:
            continue
        if peer_types & SPEAKER_DRIVER_TYPES:
            continue
        items.append(ctx.make_item(
            code="INTERACTION_SPEAKER_DIRECT_MCU_DRIVE",
            path=f"$.nets[{ctx.net_index(first_net)}].pins" if first_net else "$.components",
            message=f"{component_id}: speaker is connected directly to an MCU output with no audio driver",
            why_it_matters="MCU GPIO pins typically cannot source enough current to drive a speaker; direct connection risks overloading the GPIO and producing insufficient volume.",
            expected="an audio amplifier IC, transistor, or H-bridge driver between the MCU and the speaker",
            actual=f"{component_id} connected to ic_mcu with no driver in path",
            repair_hint="Insert an audio amplifier IC, transistor, or H-bridge driver between the MCU and the speaker.",
            component_id=component_id,
            component_type="speaker",
            pin_ref=f"{component_id}.1",
            net_name=str(first_net.get("name", "")) if first_net else "",
            related_component_cards=["speaker", "ic_audio_amp", "ic_driver", "transistor_npn"],
            related_rule="T3-19",
        ))
    return items


# ── Fixtures ──────────────────────────────────────────────────────────────────

def fixture_relay_no_flyback() -> dict[str, Any]:
    """Relay coil driven by transistor with no flyback diode — triggers T3-17."""
    return {
        "metadata": {"title": "Bad Relay No Flyback", "description": "Relay coil with no flyback diode.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 160},
            {"id": "K1", "type": "relay", "part": "SRD-5VDC", "value": "5V relay", "pins": {"A1": "VCC", "A2": "COIL_LOW", "NO": "OUT", "COM": "VCC", "NC": "GND"}, "x": 80, "y": 50},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "1k", "pins": {"1": "BASE_DRIVE", "2": "GND"}, "x": 60, "y": 110},
            {"id": "Q1", "type": "transistor_npn", "part": "SOT-23", "value": "NPN", "pins": {"B": "BASE_DRIVE", "C": "COIL_LOW", "E": "GND"}, "x": 120, "y": 100},
            {"id": "J1", "type": "connector", "part": "HEADER", "value": "", "pins": {"1": "OUT", "2": "GND", "3": "BASE_DRIVE"}, "x": 180, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "K1.A1", "K1.COM"]},
            {"name": "COIL_LOW", "pins": ["K1.A2", "Q1.C"]},
            {"name": "BASE_DRIVE", "pins": ["R1.1", "Q1.B", "J1.3"]},
            {"name": "OUT", "pins": ["K1.NO", "J1.1"]},
            {"name": "GND", "pins": ["GND1.1", "Q1.E", "R1.2", "K1.NC", "J1.2"]},
        ],
    }


def fixture_motor_dc_no_flyback() -> dict[str, Any]:
    """DC motor with no flyback diode — triggers T3-18."""
    return {
        "metadata": {"title": "Bad Motor No Flyback", "description": "DC motor driven without flyback diodes.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "12V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 160},
            {"id": "M1", "type": "motor_dc", "part": "DC130", "value": "12V", "pins": {"1": "VCC", "2": "GND"}, "x": 100, "y": 80},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "M1.1"]},
            {"name": "GND", "pins": ["GND1.1", "M1.2"]},
        ],
    }


def fixture_speaker_direct_mcu() -> dict[str, Any]:
    """Speaker connected directly to MCU with no audio driver — triggers T3-19."""
    return {
        "metadata": {"title": "Bad Speaker Direct MCU", "description": "Speaker driven directly from MCU GPIO.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "3V3", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 140},
            {"id": "U1", "type": "ic_mcu", "part": "QFP-32", "value": "STM32", "pins": {"VCC": "VCC", "GND": "GND", "PA5": "AUDIO_OUT"}, "x": 60, "y": 50},
            {"id": "SP1", "type": "speaker", "part": "8OHM", "value": "0.5W", "pins": {"1": "AUDIO_OUT", "2": "GND"}, "x": 160, "y": 80},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC"]},
            {"name": "AUDIO_OUT", "pins": ["U1.PA5", "SP1.1"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "SP1.2"]},
        ],
    }
