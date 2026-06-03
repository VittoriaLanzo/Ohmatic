"""Additional ERC coverage rules (T3-41 .. T3-45).

Compliance-first checks that close false-negative gaps in the core engine. Each rule
is tightly scoped to avoid flagging legitimate designs (false positives reject the
model's correct outputs and shrink ERC-clean training data, so scoping matters).

Entry point: coverage_diagnostics(ctx) — appended to _RULE_MODULES.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eval.diagnostic_rules import _Context


# Pin-name vocabularies (matched case-insensitively).
_OUT_PINS = {"OUT", "OUTPUT", "VOUT", "OUTA", "OUTB"}
_INM_PINS = {"IN-", "INM", "VIN-", "-IN", "INN", "IN-A", "IN-B"}
_INP_PINS = {"IN+", "INP", "VIN+", "+IN", "INPA", "IN+A", "IN+B"}
_SW_PINS = {"SW", "LX", "SWITCH", "SW1", "SW2", "PH", "BOOT"}
_RESET_PINS = {"RESET", "NRESET", "RST", "NRST", "RESETN", "RSTN", "MCLR", "NMCLR", "POR"}


def coverage_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    # Only rules with verified-low false-positive rates on the corpus are enabled.
    # _converter_missing_inductor (T3-42) and _i2c_missing_pullup (T3-44) were measured
    # to false-positive heavily — on charge-pump converters (flying cap, no inductor)
    # and on SPI devices whose data pin is named "SDA" — so they are intentionally NOT
    # dispatched. They remain in this module, documented, for a future tightened pass.
    items: list[dict[str, Any]] = []
    for rule in (
        _ic_missing_ground_pin,        # T3-41
        _mcu_reset_floating,           # T3-45
    ):
        items.extend(rule(ctx))
    return items


def _find_pin(pins: dict, vocab: set) -> str | None:
    for p in pins:
        if str(p).upper() in vocab:
            return p
    return None


# ── T3-41: IC has no ground-pin connection ────────────────────────────────────

# IC types that legitimately may have NO dedicated ground pin (3-terminal adjustable
# regulators reference ground through their ADJ pin, not a GND pin). Exempt from T3-41.
_GND_PIN_EXEMPT = {"ic_regulator"}


def _ic_missing_ground_pin(ctx: "_Context") -> list[dict[str, Any]]:
    from eval.diagnostic_rules import IC_TYPES_WITH_VCC, _is_ground_net

    grounded: set[str] = set()
    for net in ctx.nets:
        if _is_ground_net(ctx, net):
            grounded |= ctx.comps_on_net(net)

    items = []
    for comp in ctx.components:
        ctype = comp.get("type")
        if ctype not in IC_TYPES_WITH_VCC or ctype in _GND_PIN_EXEMPT:
            continue
        cid = str(comp.get("id", ""))
        if cid in grounded:
            continue
        items.append(ctx.make_item(
            code="POWER_IC_MISSING_GROUND_PIN",
            path="$.nets",
            message=f"{cid}: IC has no pin connected to a ground net",
            why_it_matters="An IC with no ground return has no current return path and cannot function; the complement of the supply-rail check.",
            expected="one IC ground pin connected to a GND-type net (power_gnd / GND / VSS)",
            actual=f"{cid} not present on any ground net",
            repair_hint="Connect the IC ground pin to the GND net.",
            component_id=cid,
            component_type=str(comp.get("type", "")),
            net_name="GND",
            related_component_cards=[str(comp.get("type", "")), "power_gnd"],
            related_rule="T3-41",
            severity="error",
        ))
    return items


# ── T3-42: switching converter without an inductor on its switch node ─────────

def _converter_missing_inductor(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for comp in ctx.components_of_type("ic_power_converter"):
        cid = str(comp.get("id", ""))
        pins = comp.get("pins", {})
        sw_pin = _find_pin(pins, _SW_PINS)
        if not sw_pin:
            continue  # integrated-inductor / LDO / charge-pump — no external L expected
        net = ctx.net_for_pin(f"{cid}.{sw_pin}")
        if not net:
            continue
        if any(ctx.component_type(c) == "inductor" for c in ctx.comps_on_net(net)):
            continue
        items.append(ctx.make_item(
            code="POWER_CONVERTER_MISSING_INDUCTOR",
            path="$.components",
            message=f"{cid}: switching converter has no inductor on switch node '{net.get('name','')}'",
            why_it_matters="A buck/boost converter needs an external inductor on its switch node to transfer energy; without it the output is wrong and the switch can be damaged.",
            expected="an inductor connected to the converter SW/LX node",
            actual=f"{cid}.{sw_pin} on '{net.get('name','')}' with no inductor",
            repair_hint="Add an inductor from the converter switch node to the output/input per the datasheet.",
            component_id=cid,
            component_type=str(comp.get("type", "")),
            net_name=str(net.get("name", "")),
            related_component_cards=["ic_power_converter", "inductor"],
            related_rule="T3-42",
            severity="error",
        ))
    return items


# ── T3-43: op-amp with no feedback path (open-loop misuse) ────────────────────

def _opamp_missing_feedback(ctx: "_Context") -> list[dict[str, Any]]:
    items = []
    for comp in ctx.components_of_type("ic_opamp"):
        cid = str(comp.get("id", ""))
        pins = comp.get("pins", {})
        out_pin = _find_pin(pins, _OUT_PINS)
        inm_pin = _find_pin(pins, _INM_PINS)
        inp_pin = _find_pin(pins, _INP_PINS)
        if not out_pin or (not inm_pin and not inp_pin):
            continue
        out_net = ctx.net_for_pin(f"{cid}.{out_pin}")
        if not out_net:
            continue
        inm_net = ctx.net_for_pin(f"{cid}.{inm_pin}") if inm_pin else None
        inp_net = ctx.net_for_pin(f"{cid}.{inp_pin}") if inp_pin else None
        # Voltage follower: OUT tied directly to IN- (same net) is valid feedback.
        if inm_net is out_net or inp_net is out_net:
            continue
        out_comps = ctx.comps_on_net(out_net)
        # FP guard: feedback may close through a connector / off-board network.
        if any(ctx.component_type(c) == "connector" for c in out_comps):
            continue
        in_comps: set[str] = set()
        if inm_net:
            in_comps |= ctx.comps_on_net(inm_net)
        if inp_net:
            in_comps |= ctx.comps_on_net(inp_net)
        if (out_comps & in_comps) - {cid}:
            continue  # a component bridges OUT back to an input → feedback exists
        items.append(ctx.make_item(
            code="INTERACTION_OPAMP_MISSING_FEEDBACK",
            path="$.components",
            message=f"{cid}: op-amp output has no feedback path to either input (open-loop)",
            why_it_matters="An op-amp without feedback runs open-loop and saturates to a rail; an amplifier/filter/buffer will not function as designed.",
            expected="a feedback component from OUT to IN- (or a follower with OUT tied to IN-)",
            actual=f"{cid} OUT '{out_net.get('name','')}' shares no component with either input net",
            repair_hint="Add a feedback resistor/capacitor from OUT to IN-, or tie OUT to IN- for a unity buffer. If this is a comparator, use type ic_comparator.",
            component_id=cid,
            component_type="ic_opamp",
            net_name=str(out_net.get("name", "")),
            related_component_cards=["ic_opamp", "resistor"],
            related_rule="T3-43",
            severity="error",
        ))
    return items


# ── T3-44: I2C bus with no pull-up resistor ───────────────────────────────────

def _i2c_missing_pullup(ctx: "_Context") -> list[dict[str, Any]]:
    from eval.diagnostic_rules import IC_TYPES_WITH_VCC, _net_has_resistor_to_vcc

    items = []
    seen: set[int] = set()
    for comp in ctx.components:
        if comp.get("type") not in IC_TYPES_WITH_VCC:
            continue
        cid = str(comp.get("id", ""))
        for pin_name in comp.get("pins", {}):
            if str(pin_name).upper() not in ("SDA", "SCL"):
                continue
            net = ctx.net_for_pin(f"{cid}.{pin_name}")
            if not net or id(net) in seen:
                continue
            seen.add(id(net))
            # Require a real shared bus (≥2 components) — a lone pin is not a bus.
            if len(ctx.comps_on_net(net)) < 2:
                continue
            if _net_has_resistor_to_vcc(ctx, net):
                continue
            items.append(ctx.make_item(
                code="INTERACTION_I2C_MISSING_PULLUP",
                path=f"$.nets[{ctx.net_index(net)}].pins",
                message=f"I2C net '{net.get('name','')}' ({str(pin_name).upper()}) has no pull-up resistor to a supply rail",
                why_it_matters="I2C is open-drain: without pull-up resistors SDA/SCL never reach logic-high and all bus communication fails.",
                expected="a pull-up resistor from the SDA/SCL net to a positive supply rail",
                actual=f"'{net.get('name','')}' has no resistor to VCC",
                repair_hint="Add a pull-up resistor (typically 4.7k) from this I2C line to VCC/3V3.",
                net_name=str(net.get("name", "")),
                related_component_cards=["resistor", "ic_mcu"],
                related_rule="T3-44",
                severity="error",
            ))
    return items


# ── T3-45: MCU reset pin with no pull-up ──────────────────────────────────────

def _reset_is_driven(ctx: "_Context", net: dict, mcu_id: str) -> bool:
    """True if the reset net is actively driven by another IC (supervisor/brownout) or
    a debug connector (JTAG/SWD) — directly on the net, or through one series resistor.
    Such resets are valid without a pull-up."""
    def _has_driver(n: dict) -> bool:
        for o in ctx.comps_on_net(n) - {mcu_id}:
            t = ctx.component_type(o)
            if t.startswith("ic_") or t == "connector":
                return True
        return False

    if _has_driver(net):
        return True
    # Driven through a series resistor on the reset net.
    for cid in ctx.comps_on_net(net):
        if ctx.component_type(cid) != "resistor":
            continue
        comp = ctx.by_id.get(cid, {})
        for pin in comp.get("pins", {}):
            other = ctx.net_for_pin(f"{cid}.{pin}")
            if other is not None and other is not net and _has_driver(other):
                return True
    return False


def _mcu_reset_floating(ctx: "_Context") -> list[dict[str, Any]]:
    from eval.diagnostic_rules import _net_has_resistor_to_vcc, _is_positive_supply_net

    items = []
    for comp in ctx.components_of_type("ic_mcu"):
        cid = str(comp.get("id", ""))
        for pin_name in comp.get("pins", {}):
            norm = str(pin_name).upper().replace("#", "").replace("/", "").replace("-", "").replace("_", "")
            if norm not in _RESET_PINS:
                continue
            net = ctx.net_for_pin(f"{cid}.{pin_name}")
            if not net:
                continue
            # Tied directly to a supply rail (held high) is acceptable.
            if _is_positive_supply_net(ctx, net):
                continue
            if _net_has_resistor_to_vcc(ctx, net):
                continue
            # Actively DRIVEN reset needs no pull-up. Exempt when a reset supervisor /
            # brownout detector (another IC) or a debug connector (JTAG/SWD) drives the
            # reset — either directly on the net OR through a series resistor.
            if _reset_is_driven(ctx, net, cid):
                continue
            items.append(ctx.make_item(
                code="INTERACTION_MCU_RESET_FLOATING",
                path=f"$.nets[{ctx.net_index(net)}].pins",
                message=f"{cid}: reset pin '{pin_name}' on net '{net.get('name','')}' has no pull-up resistor",
                why_it_matters="An active-low MCU reset pin must be pulled high; a floating reset picks up noise and causes random resets.",
                expected="a pull-up resistor from the reset net to a positive supply rail",
                actual=f"{cid}.{pin_name} on '{net.get('name','')}' with no pull-up",
                repair_hint="Add a pull-up resistor (typically 10k) from the reset pin to VCC.",
                component_id=cid,
                component_type="ic_mcu",
                net_name=str(net.get("name", "")),
                related_component_cards=["ic_mcu", "resistor"],
                related_rule="T3-45",
                severity="warning",
            ))
            break  # one reset diagnostic per MCU
    return items
