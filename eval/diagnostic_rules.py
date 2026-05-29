"""Electrical and interaction diagnostic rules for Ohmatic circuits.

Architecture
------------
All rule checks share a single ``_Context`` object that precomputes O(1)
lookup indices (pin→net, type→components, net→types, net→index) on
construction.  Individual rule modules live in ``eval/rules/`` and receive
the shared context; they never re-scan the full component or net list.

To add new rule modules:
  1.  Create ``eval/rules/your_rules.py`` with a ``your_diagnostics(ctx)``
      entry-point function.
  2.  Import it here and append it to ``_RULE_MODULES``.
  3.  Add the new error codes to ``eval/error_taxonomy.json``.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable

from eval.rules.power_rules import power_regulation_diagnostics
from eval.rules.transistor_rules import transistor_diagnostics
from eval.rules.inductive_rules import inductive_diagnostics
from eval.rules.protection_rules import protection_diagnostics
from eval.rules.switch_display_rules import switch_display_diagnostics
from eval.rules.ic_specific_rules import ic_specific_diagnostics
from eval.rules.polarity_power_rules import polarity_power_diagnostics

DiagnosticFactory = Callable[..., dict[str, Any]]

# ── Shared type-set constants (used by multiple rules) ────────────────────────

GATE_DRIVER_TYPES: frozenset[str] = frozenset({
    "resistor", "power_vcc", "power_gnd", "ic_driver", "ic_logic", "ic_mcu", "connector",
})

# All IC component types that should have a VCC pin and therefore need bypass
# capacitors (T3-04) and a literal VCC net (T3-06).
IC_TYPES_WITH_VCC: frozenset[str] = frozenset({
    # Original 6
    "ic_opamp", "ic_timer", "ic_regulator", "ic_logic", "ic_mcu", "ic_driver",
    # Extended — all registry IC types with supply pins
    "ic_comparator", "ic_adc", "ic_dac", "ic_memory", "ic_eeprom",
    "ic_rtc", "ic_audio_amp", "ic_power_converter", "ic_bms",
    "ic_battery_charger", "ic_display_driver", "ic_encoder",
    "ic_protection", "level_shifter", "voltage_ref",
})

# Components exempt from the isolation check (T3-07).  These are boundary /
# passive devices that don't need a traced path back to VCC or GND.
T3_07_EXEMPT: frozenset[str] = frozenset({
    "power_vcc", "power_gnd", "connector", "button", "crystal", "speaker",
    "sensor", "inductor", "battery", "antenna", "microphone", "motor_dc",
    "motor_stepper", "servo", "transformer",
})

# ── Rule module registry — append here to add new domains ─────────────────────
# Each entry is a callable: (ctx: _Context) -> list[dict[str, Any]]
_RULE_MODULES: list[Callable] = [
    power_regulation_diagnostics,    # T3-09 → T3-12
    transistor_diagnostics,          # T3-13 → T3-16
    inductive_diagnostics,           # T3-17 → T3-19
    protection_diagnostics,          # T3-20 → T3-23
    switch_display_diagnostics,      # T3-24, T3-25, T3-27, T3-28, T3-36
    ic_specific_diagnostics,         # T3-26, T3-29, T3-37, T3-38, T3-39, T3-40
    polarity_power_diagnostics,      # T3-30, T3-32, T3-33, T3-34, T3-35
]


def _extract_topology(circuit: dict[str, Any]) -> tuple[list, list]:
    """Return (components, nets) from either flat or STAGE_1_TOPOLOGY format."""
    if "STAGE_1_TOPOLOGY" in circuit:
        topo = circuit["STAGE_1_TOPOLOGY"]
        return topo.get("components", []), topo.get("nets", [])
    return circuit.get("components", []), circuit.get("nets", [])


def electrical_diagnostics(circuit: dict[str, Any], make_item: DiagnosticFactory) -> list[dict[str, Any]]:
    components, nets = _extract_topology(circuit)
    if not isinstance(components, list) or not isinstance(nets, list):
        return []
    ctx = _Context(components, nets, make_item)
    items: list[dict[str, Any]] = []
    # T3-01 → T3-08: core topology rules (inline, no sub-module)
    for rule in (
        _short_vcc_gnd,
        _led_missing_current_limit,
        _floating_mosfet_gate,
        _ic_missing_bypass,
        _reversed_capacitor,
        _ic_missing_literal_vcc,
        _isolated_component,
        _button_missing_pull,
    ):
        items.extend(rule(ctx))
    # T3-09 → T3-40: domain-specific rule modules
    for dispatcher in _RULE_MODULES:
        items.extend(dispatcher(ctx))
    return items


# ── Shared context — O(1) indices ─────────────────────────────────────────────

class _Context:
    """Shared diagnostic context.

    Precomputes four O(1) lookup indices on construction so that every rule
    function runs in O(components_of_that_type) rather than O(all_nets ×
    all_pins):

    * ``pin_to_net``  — direct pin-ref → net dict lookup
    * ``by_type``     — component type → list of component dicts
    * ``by_id``       — component id  → component dict
    * ``_net_idx``    — net identity  → position in self.nets list
    * ``_net_types``  — net identity  → set of component types (lazily cached)
    """

    def __init__(self, components: list[Any], nets: list[Any], make_item: DiagnosticFactory) -> None:
        self.components: list[dict[str, Any]] = [c for c in components if isinstance(c, dict)]
        self.nets: list[dict[str, Any]] = [n for n in nets if isinstance(n, dict)]
        self.make_item = make_item

        # id → component
        self.by_id: dict[str, dict[str, Any]] = {
            c["id"]: c for c in self.components if isinstance(c.get("id"), str)
        }

        # type → [component, …]
        self.by_type: dict[str, list[dict[str, Any]]] = {}
        for c in self.components:
            t = str(c.get("type", ""))
            if t:
                self.by_type.setdefault(t, []).append(c)

        # pin_ref → net  (built in O(total pins))
        self._pin_to_net: dict[str, dict[str, Any]] = {}
        for net in self.nets:
            for pin in net.get("pins", []):
                if isinstance(pin, str):
                    self._pin_to_net[pin] = net

        # net identity → list index  (O(1) via id())
        self._net_idx: dict[int, int] = {id(n): i for i, n in enumerate(self.nets)}

        # net identity → frozenset of component types (lazily populated)
        self._net_types: dict[int, frozenset[str]] = {}

    # ── Fast accessors ────────────────────────────────────────────────────────

    def net_for_pin(self, pin_ref: str) -> dict[str, Any] | None:
        """O(1) pin-ref → net lookup."""
        return self._pin_to_net.get(pin_ref)

    def net_has_type(self, net: dict[str, Any], component_type: str) -> bool:
        """O(1) membership check — does *net* carry a component of *component_type*?"""
        return component_type in self._types_on_net(net)

    def net_has_any_type(self, net: dict[str, Any], type_set: frozenset[str]) -> bool:
        """O(1) set-intersection check — any of *type_set* present on *net*?"""
        return bool(self._types_on_net(net) & type_set)

    def comps_on_net(self, net: dict[str, Any]) -> set[str]:
        """Return the set of component IDs (not pin IDs) whose pins are on *net*."""
        return {
            pin.split(".", 1)[0]
            for pin in net.get("pins", [])
            if isinstance(pin, str) and "." in pin
        }

    def component_type(self, component_id: str) -> str:
        return str(self.by_id.get(component_id, {}).get("type", ""))

    def net_index(self, net: dict[str, Any]) -> int:
        """O(1) net → list index."""
        return self._net_idx.get(id(net), -1)

    def components_of_type(self, *types: str) -> list[dict[str, Any]]:
        """Return all components whose type is one of *types* — O(result)."""
        out: list[dict[str, Any]] = []
        for t in types:
            out.extend(self.by_type.get(t, []))
        return out

    # ── Internal ──────────────────────────────────────────────────────────────

    def _types_on_net(self, net: dict[str, Any]) -> frozenset[str]:
        key = id(net)
        if key not in self._net_types:
            self._net_types[key] = frozenset(
                self.by_id[cid]["type"]
                for cid in self.comps_on_net(net)
                if cid in self.by_id
            )
        return self._net_types[key]


# ── T3-01 through T3-08: core topology rules ──────────────────────────────────

def _short_vcc_gnd(ctx: _Context) -> list[dict[str, Any]]:
    items = []
    for net in ctx.nets:
        if ctx.net_has_type(net, "power_vcc") and ctx.net_has_type(net, "power_gnd"):
            items.append(ctx.make_item(
                code="POWER_SHORT_VCC_GND",
                path=f"$.nets[{ctx.net_index(net)}].pins",
                message=f"net '{net.get('name', '')}' connects VCC and GND directly",
                why_it_matters="A direct VCC-to-GND short can damage the supply, copper, or connected components.",
                expected="power_vcc and power_gnd must be on separate nets with load or circuitry between them",
                actual=net.get("name", ""),
                repair_hint="Separate the power_vcc and power_gnd pins into distinct VCC and GND nets.",
                net_name=str(net.get("name", "")),
                related_component_cards=["power_vcc", "power_gnd"],
                related_rule="T3-01",
            ))
    return items


def _led_missing_current_limit(ctx: _Context) -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("led", "led_rgb"):
        component_id = str(component.get("id", ""))
        if "A" not in component.get("pins", {}):
            continue
        net = ctx.net_for_pin(f"{component_id}.A")
        if not net or ctx.net_has_type(net, "resistor"):
            continue
        pin_ref = f"{component_id}.A"
        items.append(ctx.make_item(
            code="INTERACTION_LED_MISSING_CURRENT_LIMIT",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: LED anode net '{net.get('name', '')}' has no current-limiting resistor",
            why_it_matters="An LED tied directly to a rail can overcurrent and damage the LED, driver, or supply.",
            expected="a resistor or explicit current-control element on the LED anode path",
            actual=f"{pin_ref} on {net.get('name', '')}",
            repair_hint="Insert a resistor in series with the LED anode or drive it from a current-limited stage.",
            component_id=component_id,
            component_type=str(component.get("type", "")),
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["led", "resistor"],
            related_rule="T3-02",
        ))
    return items


def _floating_mosfet_gate(ctx: _Context) -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("mosfet_n", "mosfet_p"):
        component_id = str(component.get("id", ""))
        pin_ref = f"{component_id}.G"
        net = ctx.net_for_pin(pin_ref)
        if not net:
            continue
        ids = ctx.comps_on_net(net) - {component_id}
        if any(ctx.component_type(cid) in GATE_DRIVER_TYPES for cid in ids):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_FLOATING_MOSFET_GATE",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: MOSFET gate on net '{net.get('name', '')}' has no driver or bias component",
            why_it_matters="A floating MOSFET gate can turn on unpredictably and overheat the load path.",
            expected="gate net includes a resistor, driver, logic IC, MCU, connector, VCC, or GND bias source",
            actual=f"{pin_ref} on {net.get('name', '')}",
            repair_hint="Add a gate resistor, pull-up/pull-down resistor, or explicit driver connection.",
            component_id=component_id,
            component_type=str(component.get("type", "")),
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=[str(component.get("type", "")), "resistor", "ic_driver"],
            related_rule="T3-03",
        ))
    return items


def _ic_missing_bypass(ctx: _Context) -> list[dict[str, Any]]:
    vcc_net = next((n for n in ctx.nets if n.get("name") == "VCC"), None)
    if not vcc_net or ctx.net_has_type(vcc_net, "capacitor"):
        return []
    vcc_pins = set(vcc_net.get("pins", []))
    items = []
    for component in ctx.components:
        if component.get("type") not in IC_TYPES_WITH_VCC:
            continue
        component_id = str(component.get("id", ""))
        if any(pin.startswith(f"{component_id}.") for pin in vcc_pins):
            items.append(ctx.make_item(
                code="POWER_IC_MISSING_BYPASS_CAPACITOR",
                path=f"$.nets[{ctx.net_index(vcc_net)}].pins",
                message=f"{component_id}: IC has no bypass capacitor on VCC net",
                why_it_matters="IC supply pins need local bypassing to avoid rail noise, resets, and unstable behavior.",
                expected="at least one capacitor connected from VCC to GND near the IC supply",
                actual=f"{component_id} on VCC without capacitor on VCC",
                repair_hint="Add a capacitor with one pin on VCC and the other on GND.",
                component_id=component_id,
                component_type=str(component.get("type", "")),
                net_name="VCC",
                related_component_cards=[str(component.get("type", "")), "capacitor"],
                related_rule="T3-04",
                severity="warning",
            ))
    return items


def _reversed_capacitor(ctx: _Context) -> list[dict[str, Any]]:
    gnd_net = next((n for n in ctx.nets if n.get("name") == "GND"), None)
    vcc_net = next((n for n in ctx.nets if n.get("name") == "VCC"), None)
    items = []
    for component in ctx.components_of_type("capacitor"):
        component_id = str(component.get("id", ""))
        pos_ref = f"{component_id}.1"
        neg_ref = f"{component_id}.2"
        if gnd_net and pos_ref in gnd_net.get("pins", []):
            items.append(_cap_polarity_item(ctx, component_id, pos_ref, "GND"))
        if vcc_net and neg_ref in vcc_net.get("pins", []):
            items.append(_cap_polarity_item(ctx, component_id, neg_ref, "VCC"))
    return items


def _cap_polarity_item(ctx: _Context, component_id: str, pin_ref: str, net_name: str) -> dict[str, Any]:
    return ctx.make_item(
        code="POLARITY_REVERSED_CAPACITOR",
        path="$.nets[*].pins",
        message=f"{component_id}: capacitor polarity pin {pin_ref} is connected to {net_name}",
        why_it_matters="A polarized capacitor connected backwards can leak, overheat, or fail.",
        expected="capacitor positive pin on VCC-side node and negative pin on GND-side node",
        actual=f"{pin_ref} on {net_name}",
        repair_hint="Swap the capacitor pins or move the capacitor to the correct rail orientation.",
        component_id=component_id,
        component_type="capacitor",
        pin_ref=pin_ref,
        net_name=net_name,
        related_component_cards=["capacitor"],
        related_rule="T3-05",
    )


def _ic_missing_literal_vcc(ctx: _Context) -> list[dict[str, Any]]:
    vcc_net = next((n for n in ctx.nets if n.get("name") == "VCC"), None)
    vcc_pins = set(vcc_net.get("pins", [])) if vcc_net else set()
    items = []
    for component in ctx.components:
        if component.get("type") not in IC_TYPES_WITH_VCC:
            continue
        component_id = str(component.get("id", ""))
        if any(pin.startswith(f"{component_id}.") for pin in vcc_pins):
            continue
        items.append(ctx.make_item(
            code="POWER_IC_MISSING_LITERAL_VCC_NET",
            path="$.nets",
            message=f"{component_id}: IC has no pin connected to literal VCC net",
            why_it_matters="The current Stage 1 ERC only recognizes the net named exactly VCC for IC supply checks.",
            expected="one IC supply pin connected to a net named VCC",
            actual=f"{component_id} not present on VCC net",
            repair_hint="Rename the primary positive IC rail to VCC or connect the IC supply pin to the VCC net.",
            component_id=component_id,
            component_type=str(component.get("type", "")),
            net_name="VCC",
            related_component_cards=[str(component.get("type", "")), "power_vcc"],
            related_rule="T3-06",
            severity="warning",
        ))
    return items


def _isolated_component(ctx: _Context) -> list[dict[str, Any]]:
    adj: dict[str, set[str]] = {}
    for net in ctx.nets:
        ids = [pin.split(".", 1)[0] for pin in net.get("pins", []) if isinstance(pin, str) and "." in pin]
        for left in ids:
            for right in ids:
                if left != right:
                    adj.setdefault(left, set()).add(right)

    queue: deque[str] = deque()
    reachable: set[str] = set()
    for component in ctx.components_of_type("power_vcc", "power_gnd"):
        component_id = str(component.get("id", ""))
        reachable.add(component_id)
        queue.append(component_id)
    while queue:
        current = queue.popleft()
        for nxt in adj.get(current, set()):
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)

    items = []
    for component in ctx.components:
        component_type = str(component.get("type", ""))
        component_id = str(component.get("id", ""))
        if component_type in T3_07_EXEMPT or component_id in reachable:
            continue
        items.append(ctx.make_item(
            code="CONNECTIVITY_COMPONENT_NOT_REACHABLE_FROM_POWER",
            path="$.components",
            message=f"{component_id}: component is not reachable from any power net",
            why_it_matters="Isolated components are usually disconnected schematic fragments and will not behave as requested.",
            expected="component participates in a connected circuit rooted at VCC or GND, unless it is an exempt boundary device",
            actual=f"{component_id} is isolated from power roots",
            repair_hint="Connect the component into the intended powered signal path or remove the fragment.",
            component_id=component_id,
            component_type=component_type,
            related_component_cards=[component_type] if component_type else [],
            related_rule="T3-07",
            severity="warning",
        ))
    return items


def _button_missing_pull(ctx: _Context) -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("button"):
        component_id = str(component.get("id", ""))
        pin_ref = f"{component_id}.1"
        net = ctx.net_for_pin(pin_ref)
        if not net or ctx.net_has_type(net, "resistor"):
            continue
        items.append(ctx.make_item(
            code="INTERACTION_BUTTON_MISSING_PULL_RESISTOR",
            path=f"$.nets[{ctx.net_index(net)}].pins",
            message=f"{component_id}: button has no pull-up/pull-down resistor on net '{net.get('name', '')}'",
            why_it_matters="A button signal without a pull resistor can float and read random logic values.",
            expected="button signal net includes a resistor to VCC or GND",
            actual=f"{pin_ref} on {net.get('name', '')}",
            repair_hint="Add a pull-up or pull-down resistor on the button output net.",
            component_id=component_id,
            component_type="button",
            pin_ref=pin_ref,
            net_name=str(net.get("name", "")),
            related_component_cards=["button", "resistor"],
            related_rule="T3-08",
            severity="warning",
        ))
    return items
