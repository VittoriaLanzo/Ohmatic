"""Emit an editable KiCad schematic (.kicad_sch) from an OhmaticCircuitV01.

Two design choices keep this tractable and self-contained:

1. Connectivity is carried by net labels, not drawn wires. KiCad treats same-named
   local labels as one electrical net, so placing a label at each pin's connection
   point wires the circuit by name - no routing geometry to solve. Electrically
   correct on import; the visual layout is a clean grid the user can rearrange.

2. Every component is drawn as a generic box symbol that we embed in `lib_symbols`.
   The file therefore opens on any KiCad install with no external symbol libraries,
   and the pin coordinates are fully under our control - which is what makes the
   label placement exact. Mapping the common types to stock Device:* symbols is a
   later cosmetic upgrade (see mapping.py); it does not change connectivity.

KiCad 8 schematic grammar (version 20231120). Coordinates are millimetres, page
Y-down. A placed symbol mirrors its library (Y-up) coordinates, so a pin defined at
local (lx, ly) lands at world (px + lx, py - ly): that single transform is the only
assumption here, and the connectivity test pins it down.
"""
import json
import uuid as _uuid

_GRID = 50.8          # mm between placed symbols
_COLS = 6             # symbols per row
_PIN_SPACING = 5.08   # mm between pins down a side
_BODY_HALF_W = 5.08   # mm, half the box width
_PIN_LEN = 2.54       # mm pin stub length


def _u() -> str:
    return str(_uuid.uuid4())


def _q(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _pin_layout(n: int) -> list[tuple[int, float, float, int]]:
    """Generic-symbol pins as (number, local_x, local_y, rotation_deg).

    `local_x, local_y` is the pin's connection point (its outer tip); the stub
    extends from there into the body. Left pins point right (rot 0), right pins
    point left (rot 180). Pins are numbered 1..n top-down, left column then right.
    """
    left = (n + 1) // 2
    right = n - left
    rows = max(left, right, 1)
    top = (rows - 1) / 2 * _PIN_SPACING
    tip = _BODY_HALF_W + _PIN_LEN
    out: list[tuple[int, float, float, int]] = []
    num = 0
    for i in range(left):
        num += 1
        out.append((num, -tip, top - i * _PIN_SPACING, 0))
    for i in range(right):
        num += 1
        out.append((num, tip, top - i * _PIN_SPACING, 180))
    return out


def _lib_symbol(n: int, name: str | None = None, base: str = "    ") -> str:
    """A generic n-pin box symbol definition.

    Shared, character-for-character, by two consumers: the schematic's `lib_symbols`
    cache (name `ohmatic:GENERIC_n`, default indent) and the standalone
    `ohmatic.kicad_sym` library (name `GENERIC_n`, library indent). They MUST stay
    geometrically identical or KiCad reports a symbol mismatch, so both go through
    here. `base` sets the indent of the outer `(symbol ...)`.
    """
    if name is None:
        name = f"ohmatic:GENERIC_{n}"
    i1, i2, i3, i4 = base, base + "  ", base + "    ", base + "      "
    rows = max((n + 1) // 2, n // 2, 1)
    half_h = (rows - 1) / 2 * _PIN_SPACING + _PIN_SPACING
    lines = [
        f'{i1}(symbol {_q(name)}',
        f'{i2}(pin_names (offset 1.016)) (in_bom yes) (on_board yes)',
        f'{i2}(symbol {_q(f"GENERIC_{n}_0_1")}',
        f'{i3}(rectangle (start {-_BODY_HALF_W} {half_h}) (end {_BODY_HALF_W} {-half_h})',
        f'{i4}(stroke (width 0.254) (type default)) (fill (type background)))',
        f'{i2})',
        f'{i2}(symbol {_q(f"GENERIC_{n}_1_1")}',
    ]
    for num, lx, ly, rot in _pin_layout(n):
        lines.append(
            f'{i3}(pin passive line (at {lx} {ly} {rot}) (length {_PIN_LEN})'
            f' (name "~" (effects (font (size 1.27 1.27))))'
            f' (number {_q(num)} (effects (font (size 1.27 1.27)))))'
        )
    lines.append(f'{i2})')
    lines.append(f'{i1})')
    return "\n".join(lines)


def _used_pin_counts(circuit: dict) -> list[int]:
    return sorted({max(len(c.get("pins") or {}), 1) for c in circuit["components"]})


# A schematic that references custom symbols needs the symbols' library registered,
# or KiCad's ERC warns "library not in configuration" for every symbol. So the export
# ships a project: the `.kicad_sch` below, plus the three files here register an
# `ohmatic` symbol library local to the project. KiCad then resolves it and ERC is
# clean. KIPRJMOD is KiCad's project-directory variable.
SYM_LIB_TABLE = (
    '(sym_lib_table\n  (version 7)\n'
    '  (lib (name "ohmatic")(type "KiCad")(uri "${KIPRJMOD}/ohmatic.kicad_sym")'
    '(options "")(descr "Ohmatic generated symbols"))\n)\n'
)


def symbol_library(circuit: dict) -> str:
    """`ohmatic.kicad_sym`: the generic symbols this circuit uses, as a KiCad symbol
    library. Geometry comes from the same `_lib_symbol` the schematic caches."""
    body = "\n".join(_lib_symbol(n, name=f"GENERIC_{n}", base="  ")
                     for n in _used_pin_counts(circuit))
    return ('(kicad_symbol_lib\n  (version 20231120)\n  (generator "ohmatic")\n'
            + body + "\n)\n")


def project_file(stem: str) -> str:
    """Minimal `.kicad_pro` so KiCad opens the directory as a project (and thus loads
    the project `sym-lib-table`)."""
    return json.dumps({
        "meta": {"filename": f"{stem}.kicad_pro", "version": 1},
        "schematic": {},
        "libraries": {"pinned_symbol_libs": [], "pinned_footprint_libs": []},
        "sheets": [],
    }, indent=2) + "\n"


def emit_kicad_sch(circuit: dict) -> str:
    comps = circuit["components"]
    sheet_uuid = _u()

    # (component_id, pin_name) -> net name, so each pin can claim its label.
    pin_net: dict[tuple[str, str], str] = {}
    for net in circuit["nets"]:
        for ref in net["pins"]:
            cid, _, name = ref.partition(".")
            pin_net[(cid, name)] = net["name"]

    used_pin_counts = sorted({max(len(c.get("pins") or {}), 1) for c in comps})

    body: list[str] = []
    labels: list[str] = []
    for idx, c in enumerate(comps):
        names = list((c.get("pins") or {}).keys()) or ["1"]
        n = len(names)
        px = 25.4 + (idx % _COLS) * _GRID
        py = 25.4 + (idx // _COLS) * _GRID
        layout = {num: (lx, ly, rot) for num, lx, ly, rot in _pin_layout(n)}

        body.append(
            f'  (symbol (lib_id {_q(f"ohmatic:GENERIC_{n}")}) (at {px} {py} 0) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no) (uuid {_q(_u())})\n'
            f'    (property "Reference" {_q(c["id"])} (at {px} {py - 7.62} 0)\n'
            f'      (effects (font (size 1.27 1.27))))\n'
            f'    (property "Value" {_q(c.get("value") or c["type"])} '
            f'(at {px} {py + 7.62} 0)\n'
            f'      (effects (font (size 1.27 1.27))))\n'
            + "".join(f'    (pin {_q(k)} (uuid {_q(_u())}))\n' for k in range(1, n + 1))
            + f'    (instances (project "ohmatic"\n'
            f'      (path {_q("/" + sheet_uuid)} (reference {_q(c["id"])}) (unit 1))))\n'
            f'  )'
        )

        for num, name in enumerate(names, 1):
            net = pin_net.get((c["id"], name))
            if net is None:
                continue  # unconnected pin: no label, KiCad flags it on ERC
            lx, ly, rot = layout[num]
            wx, wy = px + lx, py - ly
            justify = "right" if lx < 0 else "left"
            labels.append(
                f'  (label {_q(net)} (at {wx} {wy} 0)\n'
                f'    (effects (font (size 1.27 1.27)) (justify {justify} bottom))'
                f' (uuid {_q(_u())}))'
            )

    out = [
        "(kicad_sch",
        "  (version 20231120)",
        '  (generator "ohmatic")',
        '  (generator_version "8.0")',
        f"  (uuid {_q(sheet_uuid)})",
        '  (paper "A4")',
        "  (lib_symbols",
        *[_lib_symbol(n) for n in used_pin_counts],
        "  )",
        *body,
        *labels,
        '  (sheet_instances (path "/" (page "1")))',
        ")",
    ]
    return "\n".join(out) + "\n"
