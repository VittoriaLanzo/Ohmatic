"""Gateway BOM-layer wiring: a deterministic parts_list in the finished job result,
and the disclosed procurement endpoints (supplier link-out matches + Jameco preflight).

The gateway stub is not a package, so it is loaded by path. The pure procurement and
parts_list logic is covered in their own tests; here we only assert the gateway exposes
and delegates to them correctly."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_gateway():
    spec = importlib.util.spec_from_file_location(
        "ohmatic_gateway_server", ROOT / "gateway" / "stub" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATEWAY = _load_gateway()


def _sample_circuit():
    return {
        "metadata": {"title": "t", "version": "0.1"},
        "components": [
            {"id": "R1", "type": "resistor", "value": "10k", "part": "0603"},
            {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC"},
            {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND"},
        ],
        "nets": [],
    }


def test_parts_list_for_returns_rows_in_component_order():
    rows, ms = GATEWAY._parts_list_for(_sample_circuit())
    assert [row["id"] for row in rows] == ["R1", "VCC1", "GND1"]
    assert rows[0]["buyable"] is True   # resistor is physical
    assert rows[1]["buyable"] is False  # power symbol is not buyable
    assert ms >= 0


def test_parts_list_for_never_raises_on_unknown_type():
    bad = {"components": [{"id": "X1", "type": "not_a_real_type", "value": "", "part": ""}]}
    rows, ms = GATEWAY._parts_list_for(bad)
    assert rows == []
    assert ms == 0


class _Server:
    """Run the real gateway handler on an ephemeral port for the duration of a test."""

    def __enter__(self):
        self.srv = GATEWAY.GatewayServer(("127.0.0.1", 0), GATEWAY.Handler)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp:
            return resp.status, json.loads(resp.read())

    def post(self, path, obj):
        data = json.dumps(obj).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())


def test_jameco_preflight_route_reports_readiness():
    with _Server() as server:
        status, body = server.get("/v1/procurement/suppliers/jameco/preflight")
    assert status == 200
    assert body["supplier"] == "jameco"
    assert isinstance(body["ready_for_live_lookup"], bool)
    assert "storefront scraping" in body["never_allowed"]


def test_procurement_matches_route_rejects_missing_parts_list():
    with _Server() as server:
        status, body = server.post("/v1/procurement/matches", {})
    assert status == 400
    assert body == {"error": "missing 'parts_list' field"}


def test_procurement_matches_route_returns_disclosed_linkouts():
    parts = [
        {"id": "C1", "buyable": True, "parts_list_part": "capacitor",
         "value": "100nF", "package": "0603"},
    ]
    with _Server() as server:
        status, body = server.post(
            "/v1/procurement/matches", {"parts_list": parts, "supplier": "digikey"}
        )
    assert status == 200
    assert body["procurement_status"] == "links_ready"
    assert len(body["link_actions"]) == 1
    action = body["link_actions"][0]
    assert action["part_id"] == "C1"
    assert "digikey" in action["url"]


def test_health_remains_unversioned_and_ok():
    with _Server() as server:
        status, body = server.get("/health")
    assert status == 200
    assert body == {"status": "ok"}
