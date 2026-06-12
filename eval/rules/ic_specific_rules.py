"""IC-specific ERC rules - T3-26, T3-29, T3-37, T3-38, T3-39, T3-40."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from eval.diagnostic_rules import _Context

SUPPLY_POWER_TYPES = {"power_vcc", "power_3v3", "power_5v", "power_12v"}


def ic_specific_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    """Entry point called from diagnostic_rules.electrical_diagnostics."""
    items: list[dict[str, Any]] = []
    for rule in (
        _comparator_open_drain_missing_pull,
        _rtc_missing_battery,
        _voltage_ref_missing_bypass,
        _microphone_missing_decoupling,
        _dac_output_missing_bypass,
        _level_shifter_same_rail,
    ):
        items.extend(rule(ctx))
    return items


def _comparator_open_drain_missing_pull(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-26: ic_comparator output pin without a pull-up resistor to VCC.

    Bug-proofed: only a resistor whose OTHER pin is on a VCC-type net counts
    as a pull-up.  A hysteresis resistor (OUT→IN+), a pull-down (OUT→GND),
    or a load resistor (OUT→signal) do NOT satisfy the rule.
    """
    from eval.diagnostic_rules import _net_has_resistor_to_vcc
    items = []
    for component in ctx.components_of_type("ic_comparator"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "OUT" not in pins:
            continue
        pin_ref = f"{component_id}.OUT"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        if _net_has_resistor_to_vcc(ctx, net):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_COMPARATOR_OPEN_DRAIN_MISSING_PULL",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: comparator OUT net '{net.get('name', '')}' has no pull-up resistor",
            why_it_matters="Open-drain comparator outputs float high without a pull-up; the logic level will be indeterminate and may cause false triggers downstream.",
            expected="a pull-up resistor from the comparator OUT pin to VCC or a defined logic rail",
            actual=f"{pin_ref} on '{net.get('name', '')}' with no resistor",
            repair_hint="Add a pull-up resistor (typically 4.7 kΩ-10 kΩ) from the comparator OUT pin to VCC.",
            component_id=component_id,
            component_type="ic_comparator",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["ic_comparator", "resistor"],
            related_rule="T3-26",
        ))
    return items


def _rtc_missing_battery(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-29: ic_rtc has no battery or supercap backup on VBAT pin."""
    BATTERY_TYPES = {"battery", "capacitor"}
    items = []
    for component in ctx.components_of_type("ic_rtc"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "VBAT" not in pins:
            continue
        pin_ref = f"{component_id}.VBAT"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        peers = ctx.comps_on_net(net) - {component_id}
        has_backup = any(ctx.component_type(cid) in BATTERY_TYPES for cid in peers)
        if has_backup:
            continue
        items.append(ctx.make_item(
            code="INTERACTION_RTC_MISSING_BATTERY_BACKUP",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: ic_rtc VBAT net '{net.get('name', '')}' has no battery or supercapacitor backup",
            why_it_matters="An RTC without a backup power source loses the time and date the moment main power is removed, defeating the purpose of using an RTC.",
            expected="a battery or supercapacitor on the VBAT pin to maintain timekeeping when main power is off",
            actual=f"{pin_ref} on '{net.get('name', '')}' with no backup source",
            repair_hint="Connect a coin-cell battery (e.g., CR2032) or supercapacitor to the VBAT pin with a blocking diode if required.",
            component_id=component_id,
            component_type="ic_rtc",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["ic_rtc", "battery", "capacitor"],
            related_rule="T3-29",
        ))
    return items


def _voltage_ref_missing_bypass(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-37: voltage_ref output pin has no bypass/filter capacitor."""
    items = []
    for component in ctx.components_of_type("ic_voltage_ref", "voltage_ref"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "OUT" not in pins:
            continue
        pin_ref = f"{component_id}.OUT"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        if ctx.net_has_type(net, "capacitor"):
            continue
        items.append(ctx.make_item(
            code="POWER_VOLTAGE_REF_MISSING_BYPASS_CAPACITOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: voltage_ref OUT net '{net.get('name', '')}' has no bypass capacitor",
            why_it_matters="Precision voltage references are sensitive to load transients and RF noise; a bypass capacitor at the output is required for stable reference voltage.",
            expected="a bypass capacitor (typically 100 nF-10 µF) on the voltage reference output",
            actual=f"{pin_ref} on '{net.get('name', '')}' with no capacitor",
            repair_hint="Add a ceramic bypass capacitor (100 nF) close to the voltage reference OUT pin.",
            component_id=component_id,
            component_type="voltage_ref",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["voltage_ref", "capacitor"],
            related_rule="T3-37",
            severity="warning",
        ))
    return items


def _microphone_missing_decoupling(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-38: microphone VCC or VOUT net has no decoupling capacitor."""
    items = []
    for component in ctx.components_of_type("microphone"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        checked_nets: set[int] = set()
        for supply_pin in ("VCC", "VOUT", "OUT"):
            if supply_pin not in pins:
                continue
            pin_ref = f"{component_id}.{supply_pin}"
            net = ctx.net_for_pin(pin_ref)
            if not net:
                continue
            net_idx = ctx.net_index(net)
            if net_idx in checked_nets:
                continue
            checked_nets.add(net_idx)
            if ctx.net_has_type(net, "capacitor"):
                continue
            items.append(ctx.make_item(
                code="INTERACTION_MICROPHONE_MISSING_DECOUPLING",
                path=f"$.nets[{net_idx}].pins",
                message=f"{component_id}: microphone {supply_pin} net '{net.get('name', '')}' has no decoupling capacitor",
                why_it_matters="Electret and MEMS microphones need supply decoupling; noise on the bias line couples directly into the audio signal and causes audible hum or distortion.",
                expected="a decoupling capacitor (typically 1 µF-10 µF) on the microphone supply or output net",
                actual=f"{pin_ref} on '{net.get('name', '')}' with no capacitor",
                repair_hint="Add a decoupling capacitor between the microphone supply/output pin and GND.",
                component_id=component_id,
                component_type="microphone",
                pin_ref=pin_ref,
                net_name=str(net.get("name", "")),
                related_component_cards=["microphone", "capacitor"],
                related_rule="T3-38",
                severity="warning",
            ))
    return items


def _dac_output_missing_bypass(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-39: ic_dac VOUT net has no bypass/filter capacitor."""
    items = []
    for component in ctx.components_of_type("ic_dac"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "VOUT" not in pins and "OUT" not in pins:
            continue
        out_pin = "VOUT" if "VOUT" in pins else "OUT"
        pin_ref = f"{component_id}.{out_pin}"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        if ctx.net_has_type(net, "capacitor"):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_DAC_OUTPUT_MISSING_FILTER_CAPACITOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: ic_dac {out_pin} net '{net.get('name', '')}' has no output filter capacitor",
            why_it_matters="DAC outputs contain quantization noise and clock harmonics; a filter capacitor is required to smooth the stepped waveform before it reaches an analog load.",
            expected="a filter/bypass capacitor on the DAC output net to reduce high-frequency noise",
            actual=f"{pin_ref} on '{net.get('name', '')}' with no capacitor",
            repair_hint="Add a capacitor (e.g., 100 nF) at the DAC output, or design a proper RC low-pass filter appropriate for the output frequency range.",
            component_id=component_id,
            component_type="ic_dac",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["ic_dac", "capacitor"],
            related_rule="T3-39",
            severity="warning",
        ))
    return items


def _level_shifter_same_rail(ctx: "_Context") -> list[dict[str, Any]]:
    """T3-40: level_shifter VCCA and VCCB on the same net - no level shifting occurs."""
    items = []
    for component in ctx.components_of_type("ic_level_shifter", "level_shifter"):
        component_id = str(component.get("id", ""))
        pins = component.get("pins", {})
        if "VCCA" not in pins or "VCCB" not in pins:
            continue
        net_a = ctx.net_for_pin(f"{component_id}.VCCA")
        net_b = ctx.net_for_pin(f"{component_id}.VCCB")
        if not net_a or not net_b:
            continue
        if net_a is net_b or net_a.get("name") == net_b.get("name"):
            items.append(ctx.make_item(
                code="INTERACTION_LEVEL_SHIFTER_SAME_VOLTAGE_RAILS",
                path=f"$.nets[{ctx.net_index(net_a)}].pins",
                message=f"{component_id}: level_shifter VCCA and VCCB are both on net '{net_a.get('name', '')}' - no voltage difference exists",
                why_it_matters="A bidirectional level shifter with identical voltage on both supply rails performs no translation; signal integrity is not guaranteed and the design intent is likely wrong.",
                expected="VCCA and VCCB connected to different voltage rails (e.g., 3.3 V and 5 V) to achieve level shifting",
                actual=f"VCCA and VCCB both on '{net_a.get('name', '')}'",
                repair_hint="Connect VCCA to one logic rail (e.g., 3.3 V) and VCCB to the other (e.g., 5 V), or replace the level shifter with a direct connection if the rails are truly identical.",
                component_id=component_id,
                component_type="level_shifter",
                pin_ref=f"{component_id}.VCCA",
                net_name=str(net_a.get("name", "")),
                related_component_cards=["level_shifter"],
                related_rule="T3-40",
            ))
    return items


# ── Fixtures ──────────────────────────────────────────────────────────────────

def fixture_comparator_no_pullup() -> dict[str, Any]:
    """Comparator open-drain output with no pull-up - triggers T3-26."""
    return {
        "metadata": {"title": "Bad Comparator No Pull-Up", "description": "Open-drain comparator output floating.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 160},
            {"id": "U1", "type": "ic_comparator", "part": "LM393", "value": "LM393", "pins": {"IN+": "SIG_P", "IN-": "SIG_N", "OUT": "COMP_OUT", "VCC": "VCC", "GND": "GND"}, "x": 80, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND"]},
            {"name": "SIG_P", "pins": ["U1.IN+"]},
            {"name": "SIG_N", "pins": ["U1.IN-"]},
            {"name": "COMP_OUT", "pins": ["U1.OUT"]},
        ],
    }


def fixture_rtc_no_battery() -> dict[str, Any]:
    """RTC without battery backup on VBAT - triggers T3-29."""
    return {
        "metadata": {"title": "Bad RTC No Battery", "description": "RTC with VBAT tied directly to VCC without backup battery.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "3V3", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 160},
            {"id": "U1", "type": "ic_rtc", "part": "DS3231", "value": "DS3231", "pins": {"VCC": "VCC", "GND": "GND", "VBAT": "VCC", "SDA": "SDA", "SCL": "SCL"}, "x": 80, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCC", "U1.VBAT"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND"]},
            {"name": "SDA", "pins": ["U1.SDA"]},
            {"name": "SCL", "pins": ["U1.SCL"]},
        ],
    }


def fixture_voltage_ref_no_bypass() -> dict[str, Any]:
    """Voltage reference output with no bypass cap - triggers T3-37."""
    return {
        "metadata": {"title": "Bad VRef No Bypass", "description": "Voltage reference output without bypass capacitor.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 160},
            {"id": "U1", "type": "voltage_ref", "part": "REF02", "value": "5V ref", "pins": {"IN": "VCC", "OUT": "VREF_OUT", "GND": "GND"}, "x": 80, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.IN"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND"]},
            {"name": "VREF_OUT", "pins": ["U1.OUT"]},
        ],
    }


def fixture_level_shifter_same_rail() -> dict[str, Any]:
    """Level shifter VCCA and VCCB on same rail - triggers T3-40."""
    return {
        "metadata": {"title": "Bad Level Shifter Same Rail", "description": "Level shifter with both supply rails at the same voltage.", "version": "0.1", "tags": ["fixture"]},
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "3V3", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 160},
            {"id": "U1", "type": "level_shifter", "part": "TXB0108", "value": "8-bit", "pins": {"VCCA": "VCC", "VCCB": "VCC", "GND": "GND", "A1": "SIG_A", "B1": "SIG_B"}, "x": 80, "y": 60},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.VCCA", "U1.VCCB"]},
            {"name": "GND", "pins": ["GND1.1", "U1.GND"]},
            {"name": "SIG_A", "pins": ["U1.A1"]},
            {"name": "SIG_B", "pins": ["U1.B1"]},
        ],
    }
