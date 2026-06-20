"""Exporter service + KiCad emitters.

Pins two things: the HTTP/handshake contract the local UI calls (loopback bind,
Host/Origin pin, optional bearer token, capabilities), and the structural
correctness of the emitters - the netlist resolves real pin numbers and footprints,
and the schematic places a net label coincident with every connected pin so the
circuit is electrically connected by name on import.
"""
import base64
import importlib.util
import io
import json
import re
import threading
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SERVER_PATH = _ROOT / "exporter" / "stub" / "server.py"
_spec = importlib.util.spec_from_file_location("exporter_stub_server", _SERVER_PATH)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

from exporter.emit import build_export, capabilities  # noqa: E402
from exporter.emit.kicad_sch import _COLS, _GRID, _pin_layout  # noqa: E402

CIRCUIT = {
    "metadata": {"title": "LED blinker", "description": "555 astable",
                 "version": "0.1", "tags": ["timer"]},
    "components": [
        {"id": "U1", "type": "ic_timer", "value": "NE555", "part": "DIP-8",
         "x": 60, "y": 50, "pins": {"VCC": "8", "GND": "1", "IN": "2", "OUT": "3"}},
        {"id": "R1", "type": "resistor", "value": "10k", "part": "0603",
         "x": 20, "y": 20, "pins": {"1": "1", "2": "2"}},
        {"id": "C1", "type": "capacitor", "value": "10nF", "part": "0805",
         "x": 20, "y": 80, "pins": {"1": "1", "2": "2"}},
        {"id": "LED1", "type": "led", "value": "", "part": "",
         "x": 95, "y": 50, "pins": {"A": "A", "K": "K"}},
        {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
         "x": 95, "y": 10, "pins": {"1": "1"}},
        {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
         "x": 95, "y": 95, "pins": {"1": "1"}},
    ],
    "nets": [
        {"name": "VCC", "pins": ["VCC1.1", "U1.VCC", "R1.1"]},
        {"name": "GND", "pins": ["GND1.1", "U1.GND", "C1.2", "LED1.K"]},
        {"name": "OUT", "pins": ["U1.OUT", "LED1.A"]},
        {"name": "TRIG", "pins": ["U1.IN", "R1.2", "C1.1"]},
    ],
}


def _request(base, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(base + path, data=data,
                                 method="POST" if data else "GET", headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


@pytest.fixture
def ex():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield SimpleNamespace(srv=srv, base=f"http://127.0.0.1:{srv.server_address[1]}")
    srv.shutdown()


# --- emitter unit tests (no HTTP) -------------------------------------------

def test_netlist_resolves_pin_numbers_and_footprints():
    content = build_export(CIRCUIT, "netlist")["content"]
    assert content.count("(comp (ref") == len(CIRCUIT["components"])
    # NE555 VCC pin name -> physical pin number 8 (not the name).
    assert '(node (ref "U1") (pin "8"))' in content
    assert '(footprint "Resistor_SMD:R_0603_1608Metric")' in content
    assert content.count("(net (code") == len(CIRCUIT["nets"])


def _project_files(circuit):
    """Decode the kicad_project export into {name: text}."""
    result = build_export(circuit, "kicad_project")
    assert result["encoding"] == "base64"
    assert result["filename"].endswith(".zip")
    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(result["content"])))
    return {n: zf.read(n).decode("utf-8") for n in zf.namelist()}


def test_kicad_project_registers_its_symbol_library():
    """The zip is a self-contained project so KiCad ERC stays clean: a schematic, a
    project-local symbol library, the sym-lib-table that registers it, and a .kicad_pro."""
    files = _project_files(CIRCUIT)
    assert any(n.endswith(".kicad_sch") for n in files)
    assert any(n.endswith(".kicad_pro") for n in files)
    assert "ohmatic.kicad_sym" in files and "sym-lib-table" in files
    assert 'name "ohmatic"' in files["sym-lib-table"]
    # The library must contain the same generic symbols the schematic references.
    sch = next(files[n] for n in files if n.endswith(".kicad_sch"))
    for n in re.findall(r'lib_id "ohmatic:(GENERIC_\d+)"', sch):
        assert f'(symbol "{n}"' in files["ohmatic.kicad_sym"], f"{n} missing from library"


def test_schematic_labels_every_connected_pin():
    """Connectivity-by-name invariant: every (component, pin) that belongs to a net
    has a label of that net's name at the pin's computed world coordinate."""
    content = next(v for k, v in _project_files(CIRCUIT).items() if k.endswith(".kicad_sch"))

    pin_net = {}
    for net in CIRCUIT["nets"]:
        for ref in net["pins"]:
            cid, _, name = ref.partition(".")
            pin_net[(cid, name)] = net["name"]

    label_at = {}
    for nm, x, y in re.findall(
            r'\(label "([^"]+)" \(at ([\-0-9.]+) ([\-0-9.]+) 0\)', content):
        label_at.setdefault((round(float(x), 3), round(float(y), 3)), set()).add(nm)

    for idx, c in enumerate(CIRCUIT["components"]):
        names = list(c["pins"].keys())
        layout = {n: (lx, ly) for n, lx, ly, _ in _pin_layout(len(names))}
        px = 25.4 + (idx % _COLS) * _GRID
        py = 25.4 + (idx // _COLS) * _GRID
        for num, name in enumerate(names, 1):
            want = pin_net.get((c["id"], name))
            if want is None:
                continue
            lx, ly = layout[num]
            key = (round(px + lx, 3), round(py - ly, 3))
            assert want in label_at.get(key, set()), f"{c['id']}.{name} unlabelled"

    # Self-contained: generic symbols are embedded, not referenced from system libs.
    for n in (1, 2, 4):
        assert f'(symbol "ohmatic:GENERIC_{n}"' in content
    assert "(kicad_sch" in content and content.rstrip().endswith(")")


def test_capabilities_lists_both_formats():
    fmts = {f["id"] for f in capabilities()["formats"]}
    assert fmts == {"netlist", "kicad_project"}
    assert capabilities()["schema_versions"] == ["0.1"]


# --- service / handshake tests ----------------------------------------------

def test_export_endpoint_returns_named_file(ex):
    code, body = _request(ex.base, "/v1/export",
                          {"circuit": CIRCUIT, "format": "netlist"})
    assert code == 200
    assert body["filename"] == "led_blinker.net"
    assert body["content_type"] == "application/x-kicad-netlist"
    assert body["content"].startswith('(export (version "E")')


def test_default_format_is_netlist(ex):
    code, body = _request(ex.base, "/v1/export", {"circuit": CIRCUIT})
    assert code == 200 and body["filename"].endswith(".net")


def test_unknown_format_is_400(ex):
    code, body = _request(ex.base, "/v1/export",
                          {"circuit": CIRCUIT, "format": "gerber"})
    assert code == 400


def test_unsupported_schema_version_is_422(ex):
    bad = {**CIRCUIT, "metadata": {**CIRCUIT["metadata"], "version": "99.0"}}
    code, body = _request(ex.base, "/v1/export", {"circuit": bad})
    assert code == 422 and body["error"] == "unsupported_schema_version"


def test_missing_circuit_is_400(ex):
    code, _ = _request(ex.base, "/v1/export", {"format": "netlist"})
    assert code == 400


def test_capabilities_endpoint(ex):
    code, body = _request(ex.base, "/v1/export/capabilities")
    assert code == 200
    assert {f["id"] for f in body["formats"]} == {"netlist", "kicad_project"}


def test_health_is_open_and_unversioned(ex):
    code, body = _request(ex.base, "/health")
    assert code == 200 and body == {"status": "ok"}


def test_bad_host_header_is_421(ex):
    code, _ = _request(ex.base, "/v1/export", {"circuit": CIRCUIT},
                       headers={"Host": "attacker.example"})
    assert code == 421


def test_cross_origin_is_403(ex):
    code, _ = _request(ex.base, "/v1/export", {"circuit": CIRCUIT},
                       headers={"Origin": "http://evil.example"})
    assert code == 403


def test_token_required_when_configured(ex, monkeypatch):
    monkeypatch.setenv("OHMATIC_EXPORT_TOKEN", "s3cret")
    code, _ = _request(ex.base, "/v1/export", {"circuit": CIRCUIT})
    assert code == 401
    code, body = _request(ex.base, "/v1/export", {"circuit": CIRCUIT},
                          headers={"Authorization": "Bearer s3cret"})
    assert code == 200 and body["filename"].endswith(".net")


def test_health_skips_token(ex, monkeypatch):
    monkeypatch.setenv("OHMATIC_EXPORT_TOKEN", "s3cret")
    code, body = _request(ex.base, "/health")
    assert code == 200 and body == {"status": "ok"}
