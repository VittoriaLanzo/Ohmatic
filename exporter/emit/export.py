"""Format registry and dispatch for the exporter service."""
import re

from .kicad_sch import emit_kicad_sch
from .netlist import emit_netlist

SCHEMA_VERSIONS = ["0.1"]

# id -> advertised capability + emitter. The capabilities handshake serves the same
# dict (minus the callable) so a client never hard-codes a format list.
FORMATS = {
    "netlist": {
        "ext": ".net",
        "content_type": "application/x-kicad-netlist",
        "label": "KiCad netlist",
        "emit": emit_netlist,
    },
    "kicad_sch": {
        "ext": ".kicad_sch",
        "content_type": "application/x-kicad-schematic",
        "label": "KiCad schematic",
        "emit": emit_kicad_sch,
    },
}


def capabilities() -> dict:
    """What this exporter can produce - the body of GET /v1/export/capabilities."""
    return {
        "schema_versions": list(SCHEMA_VERSIONS),
        "formats": [
            {"id": fid, "ext": spec["ext"],
             "content_type": spec["content_type"], "label": spec["label"]}
            for fid, spec in FORMATS.items()
        ],
    }


def _slug(title: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (title or "").strip()).strip("_").lower()
    return s or "circuit"


def build_export(circuit: dict, fmt: str) -> dict:
    """Render `circuit` to `fmt`. Returns {filename, content_type, content}.

    Raises ValueError for an unknown format and KeyError if the circuit is missing a
    structural field (the server validates shape before calling, so KeyError here is
    a programming error, not user input).
    """
    spec = FORMATS.get(fmt)
    if spec is None:
        raise ValueError(f"unknown format {fmt!r}")
    content = spec["emit"](circuit)
    title = (circuit.get("metadata") or {}).get("title", "")
    return {
        "filename": _slug(title) + spec["ext"],
        "content_type": spec["content_type"],
        "content": content,
    }
