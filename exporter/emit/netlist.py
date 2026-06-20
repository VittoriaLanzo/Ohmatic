"""Emit a KiCad netlist (.net) from an OhmaticCircuitV01.

The netlist is the canonical hand-off into a PCB: it lists components (ref, value,
footprint) and the nets that wire their pins together. It maps almost 1:1 from our
circuit object, so it is the most robust artifact to ship first - import it into
Pcbnew (File > Import > Netlist) and route. Grammar matches what
`kicad-cli sch export netlist` produces (version "E").
"""
from .mapping import lookup


def _q(s) -> str:
    """Quote a value as a KiCad S-expression string."""
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _pin_numbers(circuit: dict) -> dict[tuple[str, str], str]:
    """(component_id, pin_name) -> KiCad pin number.

    A net references a pin by name (e.g. "U1.VCC"); the component's `pins` map gives
    that name's physical pin number (NE555 VCC -> "8"). Fall back to the name itself
    for parts whose pins are already numbered ("R1.1" -> "1").
    """
    out: dict[tuple[str, str], str] = {}
    for c in circuit["components"]:
        for name, number in (c.get("pins") or {}).items():
            out[(c["id"], name)] = str(number) if number not in (None, "") else name
    return out


def emit_netlist(circuit: dict) -> str:
    pins = _pin_numbers(circuit)
    title = (circuit.get("metadata") or {}).get("title", "")

    lines = ['(export (version "E")']
    lines.append(f'  (design (source {_q(title or "ohmatic")}) (date "") '
                 f'(tool {_q("ohmatic exporter")}))')

    lines.append("  (components")
    for c in circuit["components"]:
        lib_id, _prefix, footprint = lookup(c["type"])
        lib, part = lib_id.split(":", 1) if ":" in lib_id else ("ohmatic", lib_id)
        value = c.get("value") or c["type"]
        comp = f'    (comp (ref {_q(c["id"])}) (value {_q(value)})'
        if footprint:
            comp += f' (footprint {_q(footprint)})'
        comp += f' (libsource (lib {_q(lib)}) (part {_q(part)})))'
        lines.append(comp)
    lines.append("  )")

    lines.append("  (nets")
    for code, net in enumerate(circuit["nets"], 1):
        lines.append(f'    (net (code {_q(code)}) (name {_q(net["name"])})')
        for ref in net["pins"]:
            cid, _, name = ref.partition(".")
            number = pins.get((cid, name), name)
            lines.append(f'      (node (ref {_q(cid)}) (pin {_q(number)}))')
        lines.append("    )")
    lines.append("  )")
    lines.append(")")
    return "\n".join(lines) + "\n"
