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

import re
from collections import deque
from typing import Any, Callable

from eval.rules.power_rules import power_regulation_diagnostics
from eval.rules.transistor_rules import transistor_diagnostics
from eval.rules.inductive_rules import inductive_diagnostics
from eval.rules.protection_rules import protection_diagnostics
from eval.rules.switch_display_rules import switch_display_diagnostics
from eval.rules.ic_specific_rules import ic_specific_diagnostics
from eval.rules.polarity_power_rules import polarity_power_diagnostics
from eval.rules.coverage_rules import coverage_diagnostics

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
    "ic_protection",
    # Corrected type names (registry uses ic_ prefix)
    "ic_level_shifter",
    # NOTE: ic_voltage_ref is a shunt reference (2/3-terminal, no VCC pin) —
    # it is handled by T3-37 (_voltage_ref_missing_bypass) separately and must
    # NOT be in IC_TYPES_WITH_VCC (T3-04/T3-06 would fire spuriously).
    # Additional IC types found in corpus that need VCC bypass
    "ic_fpga", "ic_pll", "ic_filter",
})

# Positive supply-rail power symbols. An IC supply pin is satisfied by ANY of these
# rails, not only a net literally named "VCC" — real designs name rails VCC_IN,
# PLL_3V3, RF_3V3, etc. Recognizing them removes a false positive in T3-06 AND lets
# T3-04 enforce bypass capacitors on every supply rail (not just one named "VCC").
# power_vee is excluded — it is a NEGATIVE rail and never an IC positive supply.
POSITIVE_SUPPLY_SYMBOLS: frozenset[str] = frozenset({
    "power_vcc", "power_3v3", "power_5v", "power_12v",
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
    coverage_diagnostics,            # T3-41 (IC ground pin), T3-45 (MCU reset float)
]


def _extract_topology(circuit: dict[str, Any]) -> tuple[list, list]:
    """Return (components, nets) from either flat or STAGE_1_TOPOLOGY format.

    Deliberately NOT validate.resolve_circuit_topology: that resolver tolerates a
    non-dict STAGE_1_TOPOLOGY (``... or {}``) and would silently yield empty lists,
    whereas here a non-dict STAGE_1 must RAISE so _safe_rule turns it into a blocking
    ERC_RULE/ANALYZER_ERROR — an un-analyzable circuit is not ERC-clean."""
    if "STAGE_1_TOPOLOGY" in circuit:
        topo = circuit["STAGE_1_TOPOLOGY"]
        return topo.get("components", []), topo.get("nets", [])
    return circuit.get("components", []), circuit.get("nets", [])


def _safe_rule(rule: Callable[..., Any], ctx: "_Context",
               make_item: DiagnosticFactory) -> list[dict[str, Any]]:
    """Run one diagnostic rule, converting any exception into a blocking diagnostic.

    The diagnostic rules were written for well-formed circuits. The STaR harvest and
    the prod correction loop feed ARBITRARY model-generated JSON through here, which
    can be malformed (missing 'type'/'id', wrong shapes). A single rule raising must
    never abort the whole analysis (that crashes the caller). Instead we flag the
    circuit invalid — a circuit that cannot be analyzed is, by definition, not
    ERC-clean — and continue with the remaining rules.
    """
    try:
        return list(rule(ctx))
    except Exception as exc:  # noqa: BLE001 — robustness boundary, must catch all
        name = getattr(rule, "__name__", "rule")
        return [make_item(
            code="ERC_RULE_ERROR",
            path="$",
            message=f"diagnostic rule '{name}' could not evaluate this circuit "
                    f"({type(exc).__name__})",
            why_it_matters="The rule failed because the circuit is malformed or "
                           "incomplete; a circuit that cannot be analyzed cannot be "
                           "certified ERC-clean.",
            repair_hint="Ensure every component has the required 'id' and 'type' "
                        "fields and that nets reference existing component pins.",
            related_rule="ERC-ROBUST",
        )]


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
        items.extend(_safe_rule(rule, ctx, make_item))
    # T3-09 → T3-40: domain-specific rule modules
    for dispatcher in _RULE_MODULES:
        items.extend(_safe_rule(dispatcher, ctx, make_item))
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
        self._net_comps: dict[int, set[str]] = {}

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
        """Component IDs (not pin IDs) on *net*. Memoized by id(net) — called
        32x across rules; same pattern as _net_types."""
        key = id(net)
        if key not in self._net_comps:
            self._net_comps[key] = {
                pin.split(".", 1)[0]
                for pin in net.get("pins", [])
                if isinstance(pin, str) and "." in pin
            }
        return self._net_comps[key]

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
            # A component may be missing its "type" (malformed/partial model output);
            # use a truthiness guard so analysis never KeyErrors on bad input.
            self._net_types[key] = frozenset(
                self.by_id[cid]["type"]
                for cid in self.comps_on_net(net)
                if cid in self.by_id and self.by_id[cid].get("type")
            )
        return self._net_types[key]


# ── T3-01 through T3-08: core topology rules ──────────────────────────────────

_ZERO_OHM_VALUES: frozenset[str] = frozenset({"0", "0r", "0ohm", "0ω", "dnp"})


def _short_vcc_gnd(ctx: _Context) -> list[dict[str, Any]]:
    items = []

    # T3-01a: single net carries both power_vcc and power_gnd
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

    # T3-01b: 0-ohm resistor bridging VCC-type net to GND-type net
    for comp in ctx.by_type.get("resistor", []):
        value = str(comp.get("value", "")).strip().lower().replace(" ", "")
        if value not in _ZERO_OHM_VALUES:
            continue
        comp_id = str(comp.get("id", ""))
        pin_nets = [
            ctx.net_for_pin(f"{comp_id}.{pin}")
            for pin in comp.get("pins", {})
        ]
        pin_nets = [n for n in pin_nets if n is not None]
        has_vcc = any(ctx.net_has_type(n, "power_vcc") for n in pin_nets)
        has_gnd = any(ctx.net_has_type(n, "power_gnd") for n in pin_nets)
        if not (has_vcc and has_gnd):
            continue
        items.append(ctx.make_item(
            code="POWER_SHORT_VCC_GND",
            path="$.components",
            message=f"{comp_id}: 0-ohm resistor bridges a VCC-type net to a GND-type net — dead short",
            why_it_matters="A 0-ohm link between the positive rail and ground is a dead short that blows the supply or traces on power-up.",
            expected="0-ohm jumpers must not connect supply and ground rails",
            actual=f"{comp_id} (value={comp.get('value','0')}) bridges VCC and GND",
            repair_hint="Remove the 0-ohm link or replace it with a real load between supply and ground.",
            component_id=comp_id,
            component_type="resistor",
            pin_ref=f"{comp_id}.1",
            net_name="VCC/GND bridge",
            related_component_cards=["resistor"],
            related_rule="T3-01",
        ))

    return items


def _net_has_cap_to_gnd(ctx: _Context, net: dict) -> bool:
    """True iff *net* has a capacitor whose other pin lands on a GND-type net."""
    for cid in ctx.comps_on_net(net):
        if ctx.component_type(cid) != "capacitor":
            continue
        comp = ctx.by_id.get(cid, {})
        for pin_name in comp.get("pins", {}):
            other_ref = f"{cid}.{pin_name}"
            other_net = ctx.net_for_pin(other_ref)
            if other_net is net:
                continue
            if other_net and ctx.net_has_type(other_net, "power_gnd"):
                return True
    return False


def _net_has_resistor_to_vcc(ctx: _Context, net: dict) -> bool:
    """True iff *net* contains a resistor whose OTHER pin lands on a positive supply
    rail.

    This is the correct "pull-up / current-limit" check.  A resistor whose
    other end goes to GND, IN+, or any other non-supply net does NOT count.
    Supply recognition uses _is_positive_supply_net so a pull-up to a 3V3 / named /
    regulator-output rail counts, not only a literal power_vcc symbol — otherwise the
    check false-positives ("no pull-up") on the many corpus rails that aren't a
    power_vcc symbol.
    """
    for cid in ctx.comps_on_net(net):
        if ctx.component_type(cid) != "resistor":
            continue
        comp = ctx.by_id.get(cid, {})
        for pin_name in comp.get("pins", {}):
            other_ref = f"{cid}.{pin_name}"
            other_net = ctx.net_for_pin(other_ref)
            if other_net is net:
                continue                        # this pin IS on the net we're checking
            if other_net and _is_positive_supply_net(ctx, other_net):
                return True
    return False


def _led_missing_current_limit(ctx: _Context) -> list[dict[str, Any]]:
    items = []
    for component in ctx.components_of_type("led", "led_rgb"):
        component_id = str(component.get("id", ""))
        if "A" not in component.get("pins", {}):
            continue
        net = ctx.net_for_pin(f"{component_id}.A")
        if not net:
            continue
        # Fire if:
        #   (a) anode net has no resistor at all — no current limiter anywhere, or
        #   (b) anode net IS a power rail (power_vcc present) — even if unrelated
        #       resistors exist on that rail, the LED is wired directly to the supply.
        # Do NOT fire if the anode is on an intermediate net that has a series R
        # (the R may connect upstream to a transistor output, IC pin, etc. — not
        # necessarily to VCC directly).
        anode_on_power_rail = ctx.net_has_type(net, "power_vcc")
        if ctx.net_has_type(net, "resistor") and not anode_on_power_rail:
            continue  # intermediate net with series R → correctly wired
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


# Net-name patterns that denote a positive supply rail even when no power symbol is
# explicitly placed on the net (corpus convention varies: some rails are a power_vcc
# symbol, some are just a net named VCC / 3V3 / VCC_IN / PLL_3V3 / a regulator output).
# Matches: VCC*, VDD*, VBUS, AVDD/DVDD/VDDA/VDDIO, VIN, VOUT, and voltage tokens like
# 3V3, 5V, 12V, 1V8, 3.3V (as a whole token, optionally with a +/_/- delimiter).
# Deliberately does NOT match VEE/negative rails or bare signal names.
_SUPPLY_NAME_RE = re.compile(
    r"(?:^|[_\-+/])(?:VCC|VDD|VBUS|VDDA|AVDD|DVDD|VDDIO|VIN|VOUT|\+?\d+V\d*|\+?\d+\.\d+V)(?:$|[_\-/])",
    re.IGNORECASE,
)

_REGULATOR_OUTPUT_TYPES: frozenset[str] = frozenset({"ic_regulator", "ic_power_converter"})


def _name_is_supply(name: str) -> bool:
    return bool(name) and bool(_SUPPLY_NAME_RE.search(name))


def _is_positive_supply_net(ctx: _Context, net: dict) -> bool:
    """True if *net* is a positive supply rail by ANY of three signals:
    (1) carries a positive power symbol, (2) is a regulator/converter output,
    (3) its name matches a supply-rail pattern. Covers the corpus's mixed
    conventions so T3-04/T3-06 neither false-positive on PLL_3V3-style rails nor
    miss name-only or regulator-fed rails."""
    if ctx.net_has_any_type(net, POSITIVE_SUPPLY_SYMBOLS):
        return True
    if _name_is_supply(str(net.get("name", ""))):
        return True
    for cid in ctx.comps_on_net(net):
        if ctx.component_type(cid) not in _REGULATOR_OUTPUT_TYPES:
            continue
        pins = ctx.by_id.get(cid, {}).get("pins", {})
        for pin_name, pin_net_name in pins.items():
            if pin_name in ("VOUT", "OUT") and pin_net_name == net.get("name", ""):
                return True
    return False


def _positive_supply_nets(ctx: _Context) -> list[dict[str, Any]]:
    """All nets that qualify as a positive supply rail (symbol, regulator out, or name)."""
    return [n for n in ctx.nets if _is_positive_supply_net(ctx, n)]


_GROUND_NAME_RE = re.compile(r"^(?:GND|GROUND|VSS|AGND|DGND|PGND|EARTH|0V)(?:$|[_\-/].*)", re.IGNORECASE)


def _is_ground_net(ctx: _Context, net: dict) -> bool:
    """True if *net* is a ground reference: has a power_gnd symbol OR its name matches a
    ground pattern (GND/VSS/AGND/DGND/PGND/0V). Mirrors the supply-net robustness so
    ground checks don't false-positive on the corpus's name-only ground rails."""
    if ctx.net_has_type(net, "power_gnd"):
        return True
    return bool(_GROUND_NAME_RE.match(str(net.get("name", ""))))


def _ic_missing_bypass(ctx: _Context) -> list[dict[str, Any]]:
    # Compliance-first: every supply rail an IC connects to must have a local bypass
    # capacitor to GND — not only a rail literally named "VCC". This both removes the
    # old false negative (non-VCC rails were skipped entirely) and keeps the strict
    # catch (an IC on a bypass-less rail still fails).
    supply_nets = _positive_supply_nets(ctx)
    if not supply_nets:
        return []
    items = []
    for component in ctx.components:
        if component.get("type") not in IC_TYPES_WITH_VCC:
            continue
        component_id = str(component.get("id", ""))
        for net in supply_nets:
            if component_id not in ctx.comps_on_net(net):
                continue
            if _net_has_cap_to_gnd(ctx, net):
                continue
            rail = str(net.get("name", ""))
            items.append(ctx.make_item(
                code="POWER_IC_MISSING_BYPASS_CAPACITOR",
                path=f"$.nets[{ctx.net_index(net)}].pins",
                message=f"{component_id}: IC has no bypass capacitor on supply net '{rail}'",
                why_it_matters="IC supply pins need local bypassing to avoid rail noise, resets, and unstable behavior.",
                expected="at least one capacitor connected from the IC supply rail to GND",
                actual=f"{component_id} on '{rail}' without a capacitor to GND",
                repair_hint="Add a capacitor with one pin on the IC supply rail and the other on GND.",
                component_id=component_id,
                component_type=str(component.get("type", "")),
                net_name=rail,
                related_component_cards=[str(component.get("type", "")), "capacitor"],
                related_rule="T3-04",
                severity="warning",
            ))
            break  # one bypass diagnostic per IC is enough
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
    # An IC is powered if any of its pins sits on a positive supply rail (VCC, 3V3,
    # 5V, 12V) — not only a net literally named "VCC". This still fires for a genuinely
    # unpowered IC (no pin on any supply rail), so the floating-supply catch is intact.
    supply_nets = _positive_supply_nets(ctx)
    powered_ids: set[str] = set()
    for net in supply_nets:
        powered_ids |= ctx.comps_on_net(net)
    items = []
    for component in ctx.components:
        if component.get("type") not in IC_TYPES_WITH_VCC:
            continue
        component_id = str(component.get("id", ""))
        if component_id in powered_ids:
            continue
        items.append(ctx.make_item(
            code="POWER_IC_MISSING_LITERAL_VCC_NET",
            path="$.nets",
            message=f"{component_id}: IC has no pin connected to any positive supply rail",
            why_it_matters="An IC with no supply-rail connection cannot be powered and will not function.",
            expected="one IC supply pin connected to a positive supply rail (VCC / 3V3 / 5V / 12V)",
            actual=f"{component_id} not present on any supply rail",
            repair_hint="Connect the IC supply pin to a positive supply rail (e.g. a power_vcc / power_3v3 net).",
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
