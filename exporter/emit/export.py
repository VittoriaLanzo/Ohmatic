"""Format registry and dispatch for the exporter service."""
import base64
import io
import re
import zipfile

from .kicad_sch import (
    SYM_LIB_TABLE,
    emit_kicad_sch,
    project_file,
    symbol_library,
)
from .netlist import emit_netlist

SCHEMA_VERSIONS = ["0.1"]


def _slug(title: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (title or "").strip()).strip("_").lower()
    return s or "circuit"


def build_kicad_project(circuit: dict) -> bytes:
    """A self-contained KiCad project (.zip).

    The schematic uses generic `ohmatic:*` symbols, so it ships with the matching
    project-local symbol library and a `sym-lib-table` that registers it. Opened as a
    project, KiCad resolves the library and ERC is clean (no 'library not in
    configuration' warnings). Verified with kicad-cli across the dataset examples.
    """
    stem = _slug((circuit.get("metadata") or {}).get("title", ""))
    files = {
        f"{stem}.kicad_pro": project_file(stem),
        f"{stem}.kicad_sch": emit_kicad_sch(circuit),
        "ohmatic.kicad_sym": symbol_library(circuit),
        "sym-lib-table": SYM_LIB_TABLE,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# id -> advertised capability + builder. `binary` formats return bytes (base64 in the
# response); text formats return a str. The capabilities handshake serves this dict
# (minus the callables) so a client never hard-codes a format list.
FORMATS = {
    "kicad_project": {
        "ext": ".zip",
        "content_type": "application/zip",
        "label": "KiCad project",
        "binary": True,
        "build": build_kicad_project,
    },
    "netlist": {
        "ext": ".net",
        "content_type": "application/x-kicad-netlist",
        "label": "KiCad netlist",
        "binary": False,
        "build": emit_netlist,
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


def build_export(circuit: dict, fmt: str) -> dict:
    """Render `circuit` to `fmt`. Returns {filename, content_type, content, encoding}.

    `encoding` is "utf-8" for text formats (netlist) or "base64" for binary ones (the
    project zip); the client decodes accordingly before saving. Raises ValueError for
    an unknown format.
    """
    spec = FORMATS.get(fmt)
    if spec is None:
        raise ValueError(f"unknown format {fmt!r}")
    stem = _slug((circuit.get("metadata") or {}).get("title", ""))
    produced = spec["build"](circuit)
    if spec["binary"]:
        content = base64.b64encode(produced).decode("ascii")
        encoding = "base64"
    else:
        content = produced
        encoding = "utf-8"
    return {
        "filename": stem + spec["ext"],
        "content_type": spec["content_type"],
        "content": content,
        "encoding": encoding,
    }
