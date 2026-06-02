"""Switch, display, stepper, servo, and SSR ERC rules — T3-24 through T3-28, T3-36."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from eval.diagnostic_rules import _Context

STEPPER_DRIVER_TYPES = {"ic_driver", "transistor_npn", "transistor_pnp", "mosfet_n", "mosfet_p", "igbt"}
SERVO_SIGNAL_TYPES = {"ic_mcu", "ic_driver", "ic_logic", "ic_timer", "connector"}
# Segment pins that carry current and need limiting resistors
SEVEN_SEG_SEGMENT_PINS = {"A", "B", "C", "D", "E", "F", "G", "DP"}


def switch_display_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    """Entry point called from diagnostic_rules.electrical_diagnostics."""
    items: list[dict[str, Any]] = []
    for rule in (
        _motor_stepper_direct_mcu,
        _seven_segment_missing_current_limit,
        _switch_missing_pull_resistor,
        _ssr_input_missing_current_limit,
        _servo_missing_control_signal,
    ):
        items.extend(rule(ctx))
    return items


# ── T3-24: motor_stepper direct MCU drive ────────────────────────────────────

def _motor_stepper_direct_mcu(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("motor_stepper"):
        comp_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        # Collect all component IDs on all stepper coil nets
        coil_comp_ids: set[str] = set()
        first_net = None
        for pin_name in ("A+", "A-", "B+", "B-"):
            if pin_name not in pins:
                continue
            net = ctx.net_for_pin(f"{comp_id}.{pin_name}")
            if net:
                if first_net is None:
                    first_net = net
                coil_comp_ids |= ctx.comps_on_net(net)
        coil_comp_ids.discard(comp_id)
        peer_types = {ctx.component_type(cid) for cid in coil_comp_ids}
        if not peer_types & {"ic_mcu", "ic_logic"}:
            continue
        if peer_types & STEPPER_DRIVER_TYPES:
            continue
        items.append(ctx.make_item(
            code="INTERACTION_MOTOR_STEPPER_DIRECT_MCU_DRIVE",
            path=f"$.nets[{ctx.net_index(first_net)}].pins" if first_net else "$.components",
            message=f"{comp_id}: stepper motor coil is connected directly to an MCU with no stepper driver IC",
            why_it_matters="MCU GPIO pins cannot supply the current required to drive stepper coils; direct connection will permanently damage the MCU output stages.",
            expected="a stepper driver IC (e.g. DRV8825, A4988) or H-bridge transistors between MCU and motor coils",
            actual=f"{comp_id} coils connected to ic_mcu with no driver in path",
            repair_hint="Insert a dedicated stepper driver IC between the MCU step/dir outputs and the motor coil pins.",
            component_id=comp_id,
            component_type="motor_stepper",
            pin_ref=f"{comp_id}.A+",
            net_name=str(first_net.get("name", "")) if first_net else "",
            related_component_cards=["motor_stepper", "ic_driver"],
            related_rule="T3-24",
        ))
    return items


# ── T3-25: seven_segment segment pins without current-limit resistors ─────────

def _seven_segment_missing_current_limit(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("seven_segment"):
        comp_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        for seg_pin in SEVEN_SEG_SEGMENT_PINS:
            if seg_pin not in pins:
                continue
            pin_ref = f"{comp_id}.{seg_pin}"
            net = ctx.net_for_pin(pin_ref)
            if not net or ctx.net_has_type(net, "resistor"):
                continue
            items.append(ctx.make_item(
                code="INTERACTION_SEVEN_SEGMENT_MISSING_CURRENT_LIMIT",
                path=f"$.nets[{ctx.net_index(net)}].pins",
                message=f"{comp_id}: seven_segment segment pin {seg_pin} on net '{net.get('name', '')}' has no current-limiting resistor",
                why_it_matters="Seven-segment LED segments require individual current-limiting resistors; direct connection to a logic rail will overcurrent the segment and may destroy the display or driving IC.",
                expected=f"a current-limiting resistor on the net for segment pin {seg_pin}",
                actual=f"{pin_ref} on net '{net.get('name', '')}' with no resistor",
                repair_hint="Add a current-limiting resistor (typically 100Ω–470Ω depending on VCC and desired brightness) in series with each segment pin.",
                component_id=comp_id,
                component_type="seven_segment",
                pin_ref=pin_ref,
                net_name=str(net.get("name", "")),
                related_component_cards=["seven_segment", "resistor"],
                related_rule="T3-25",
            ))
    return items


# ── T3-27: switch without pull resistor ──────────────────────────────────────

def _switch_missing_pull_resistor(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("switch"):
        comp_id = str(component.get("id", ""))
        if "1" not in component.get("pins", {}):
            continue
        pin_ref = f"{comp_id}.1"
        net = ctx.net_for_pin(pin_ref)
        if not net or ctx.net_has_type(net, "resistor"):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_SWITCH_MISSING_PULL_RESISTOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{comp_id}: switch output net '{net.get('name', '')}' has no pull-up or pull-down resistor",
            why_it_matters="A switch output without a pull resistor leaves the signal line floating when the switch is open, causing undefined logic levels and erratic circuit behaviour.",
            expected="a pull-up or pull-down resistor on the switch output net",
            actual=f"{pin_ref} on net '{net.get('name', '')}' with no resistor",
            repair_hint="Add a pull-up resistor to VCC or a pull-down resistor to GND on the switch output net (typically 10kΩ).",
            component_id=comp_id,
            component_type="switch",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["switch", "resistor"],
            related_rule="T3-27",
            severity="warning",
        ))
    return items


# ── T3-28: relay_solid_state input LED without current limit ──────────────────

def _ssr_input_missing_current_limit(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("relay_solid_state"):
        comp_id = str(component.get("id", ""))
        if "IN+" not in component.get("pins", {}):
            continue
        pin_ref = f"{comp_id}.IN+"
        net = ctx.net_for_pin(pin_ref)
        if not net or ctx.net_has_type(net, "resistor"):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_SSR_INPUT_MISSING_CURRENT_LIMIT",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{comp_id}: solid-state relay IN+ net '{net.get('name', '')}' has no current-limiting resistor",
            why_it_matters="SSR input circuitry contains an internal LED; driving it without a current-limiting resistor will burn out the input optocoupler and disable the relay permanently.",
            expected="a current-limiting resistor in series with the SSR IN+ pin",
            actual=f"{pin_ref} on net '{net.get('name', '')}' with no resistor",
            repair_hint="Add a current-limiting resistor between the driving signal and IN+, sized for the SSR input current specification (typically 5–20mA).",
            component_id=comp_id,
            component_type="relay_solid_state",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["relay_solid_state", "resistor"],
            related_rule="T3-28",
        ))
    return items


# ── T3-36: servo without control signal source ───────────────────────────────

def _servo_missing_control_signal(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("servo"):
        comp_id = str(component.get("id", ""))
        if "SIG" not in component.get("pins", {}):
            continue
        pin_ref = f"{comp_id}.SIG"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        peer_ids = ctx.comps_on_net(net) - {comp_id}
        peer_types = {ctx.component_type(cid) for cid in peer_ids}
        if peer_types & SERVO_SIGNAL_TYPES:
            continue
        items.append(ctx.make_item(
            code="INTERACTION_SERVO_MISSING_CONTROL_SIGNAL",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{comp_id}: servo SIG pin on net '{net.get('name', '')}' has no PWM signal source",
            why_it_matters="A servo without a PWM control signal from an MCU, timer, or driver will not move to any commanded position and may jitter or stall unpredictably.",
            expected="servo SIG net connected to an MCU, timer IC, driver IC, logic IC, or connector",
            actual=f"{pin_ref} on net '{net.get('name', '')}' with no recognised signal source",
            repair_hint="Connect the SIG pin to a PWM-capable MCU output or dedicated RC servo controller.",
            component_id=comp_id,
            component_type="servo",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["servo", "ic_mcu", "ic_timer"],
            related_rule="T3-36",
            severity="warning",
        ))
    return items


# ── Fixtures ──────────────────────────────────────────────────────────────────

def fixture_stepper_direct_mcu() -> dict[str, Any]:
    """Stepper motor driven directly from MCU — triggers T3-24."""
    return {
        "metadata": {"title": "Bad Stepper Direct MCU", "description": "Stepper coils wired directly to MCU GPIO.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 200},
            {"id": "U1", "type": "ic_mcu", "part": "QFP-32", "value": "STM32", "pins": {"VCC": "VCC", "GND": "GND", "PA0": "COIL_AP", "PA1": "COIL_AN", "PA2": "COIL_BP", "PA3": "COIL_BN"}, "x": 60, "y": 80},
            {"id": "M1", "type": "motor_stepper", "part": "NEMA17", "value": "1.7A", "pins": {"A+": "COIL_AP", "A-": "COIL_AN", "B+": "COIL_BP", "B-": "COIL_BN"}, "x": 180, "y": 100},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC"]},
            {"name": "COIL_AP", "pins": ["U1.PA0", "M1.A+"]},
            {"name": "COIL_AN", "pins": ["U1.PA1", "M1.A-"]},
            {"name": "COIL_BP", "pins": ["U1.PA2", "M1.B+"]},
            {"name": "COIL_BN", "pins": ["U1.PA3", "M1.B-"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND"]},
        ],
    }


def fixture_seven_segment_no_resistors() -> dict[str, Any]:
    """Seven-segment display with segment pins directly on MCU — triggers T3-25."""
    return {
        "metadata": {"title": "Bad 7-Seg No Resistors", "description": "7-segment driven without current-limiting resistors.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 200},
            {"id": "U1", "type": "ic_mcu", "part": "QFP-32", "value": "STM32", "pins": {"VCC": "VCC", "GND": "GND", "PA0": "SEG_A", "PA1": "SEG_B", "PA2": "SEG_C", "PA3": "SEG_D"}, "x": 60, "y": 80},
            {"id": "DS1", "type": "seven_segment", "part": "CA", "value": "1-digit", "pins": {"A": "SEG_A", "B": "SEG_B", "C": "SEG_C", "D": "SEG_D", "E": "GND", "F": "GND", "G": "GND", "DP": "GND", "COM": "VCC"}, "x": 180, "y": 80},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC", "DS1.COM"]},
            {"name": "SEG_A", "pins": ["U1.PA0", "DS1.A"]},
            {"name": "SEG_B", "pins": ["U1.PA1", "DS1.B"]},
            {"name": "SEG_C", "pins": ["U1.PA2", "DS1.C"]},
            {"name": "SEG_D", "pins": ["U1.PA3", "DS1.D"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "DS1.E", "DS1.F", "DS1.G", "DS1.DP"]},
        ],
    }


def fixture_switch_no_pull() -> dict[str, Any]:
    """Switch output floating (no pull resistor) — triggers T3-27."""
    return {
        "metadata": {"title": "Bad Switch No Pull", "description": "Switch output with no pull resistor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "3V3", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "SW1", "type": "switch", "part": "SPST", "value": "", "pins": {"1": "SW_OUT", "2": "GND"}, "x": 80, "y": 60},
            {"id": "U1", "type": "ic_mcu", "part": "QFP", "value": "MCU", "pins": {"VCC": "VCC", "GND": "GND", "PA0": "SW_OUT"}, "x": 160, "y": 50},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC"]},
            {"name": "SW_OUT", "pins": ["SW1.1", "U1.PA0"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "SW1.2"]},
        ],
    }


def fixture_ssr_no_current_limit() -> dict[str, Any]:
    """SSR input driven directly without resistor — triggers T3-28."""
    return {
        "metadata": {"title": "Bad SSR No Input R", "description": "SSR input with no current-limiting resistor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 140},
            {"id": "U1", "type": "ic_mcu", "part": "QFP", "value": "MCU", "pins": {"VCC": "VCC", "GND": "GND", "PA0": "SSR_IN"}, "x": 60, "y": 50},
            {"id": "K1", "type": "relay_solid_state", "part": "SSR-25DA", "value": "25A", "pins": {"IN+": "SSR_IN", "IN-": "GND", "OUT+": "AC_L", "OUT-": "AC_N"}, "x": 160, "y": 70},
            {"id": "J1", "type": "connector", "part": "HEADER", "value": "", "pins": {"1": "AC_L", "2": "AC_N"}, "x": 260, "y": 80},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC"]},
            {"name": "SSR_IN", "pins": ["U1.PA0", "K1.IN+"]},
            {"name": "AC_L", "pins": ["K1.OUT+", "J1.1"]},
            {"name": "AC_N", "pins": ["K1.OUT-", "J1.2"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND", "K1.IN-"]},
        ],
    }


def fixture_servo_no_signal() -> dict[str, Any]:
    """Servo SIG pin connected to nothing useful — triggers T3-36."""
    return {
        "metadata": {"title": "Bad Servo No Signal", "description": "Servo SIG floating with no MCU or driver.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 120},
            {"id": "M1", "type": "servo", "part": "SG90", "value": "9g", "pins": {"VCC": "VCC", "GND": "GND", "SIG": "SIG_FLOAT"}, "x": 80, "y": 60},
            {"id": "R1", "type": "resistor", "part": "0603", "value": "10k", "pins": {"1": "SIG_FLOAT", "2": "GND"}, "x": 160, "y": 80},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "M1.VCC"]},
            {"name": "SIG_FLOAT", "pins": ["M1.SIG", "R1.1"]},
            {"name": "GND", "pins": ["GND1.1", "M1.GND", "R1.2"]},
        ],
    }
