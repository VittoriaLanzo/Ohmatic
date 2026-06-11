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
_RESET_PINS = {"RESET", "NRESET", "RST", "NRST", "RESETN", "RSTN", "MCLR", "NMCLR", "POR"}


def coverage_diagnostics(ctx: "_Context") -> list[dict[str, Any]]:
    # Only rules with verified-low false-positive rates on the corpus are enabled
    # (T3-42/T3-43/T3-44 false-positived heavily and were removed — see git history).
    items: list[dict[str, Any]] = []
    for rule in (
        _ic_missing_ground_pin,        # T3-41
        _mcu_reset_floating,           # T3-45
    ):
        items.extend(rule(ctx))
    return items




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
