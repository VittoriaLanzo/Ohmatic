"""Job lifecycle contract of the gateway real-model path.

The pipeline is faked; what is pinned is the HTTP contract the frontend
polls. The killswitch test guards the regression where a finished job was
reported with a status the UI did not recognize, so it polled "queued"
forever. The bind test guards against two gateways silently sharing the
port on Windows (split job stores).
"""
import importlib.util
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

_SERVER_PATH = Path(__file__).resolve().parents[1] / "gateway" / "stub" / "server.py"
_spec = importlib.util.spec_from_file_location("gateway_stub_server", _SERVER_PATH)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

_CIRCUIT = {
    "metadata": {"title": "RC low-pass", "version": "0.1"},
    "STAGE_1_TOPOLOGY": {
        "components": [
            {"id": "R1", "type": "resistor", "value": "10k", "part": "0603",
             "pins": {"1": "1", "2": "2"}},
        ],
        "nets": [{"name": "VCC", "pins": ["R1.1"]}],
    },
    "STAGE_2_LAYOUT": {"spatial_nodes": [{"id": "R1", "x": 12, "y": 34}]},
}


class _FakePipeline:
    """Mimics OhmaticPipeline's surface: on_stage, generator.progress_cb, run()."""

    def __init__(self, outcome):
        self._outcome = outcome
        self.on_stage = None
        self.generator = SimpleNamespace(progress_cb=None)

    def run(self, prompt):
        if self.on_stage:
            self.on_stage("t5", 1)
            self.on_stage("generate", 1)
        if self.generator.progress_cb:
            self.generator.progress_cb(0.5)
        if self.on_stage:
            self.on_stage("verify", 1)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _request(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def _poll_terminal(base, poll_url, deadline_s=10):
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        code, body = _request(base, poll_url)
        assert code == 200
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    pytest.fail("job did not reach a terminal status in time")


@pytest.fixture
def gw(monkeypatch):
    srv = server.GatewayServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(server, "_real_available", lambda: True)
    monkeypatch.setattr(server, "_ram_guard", lambda: None)
    server.JOBS.clear()
    yield SimpleNamespace(srv=srv, base=f"http://127.0.0.1:{srv.server_address[1]}")
    srv.shutdown()


def test_successful_job_reaches_done_with_flat_circuit(gw, monkeypatch):
    result = SimpleNamespace(ok=True, circuit=_CIRCUIT, user_message="")
    monkeypatch.setattr(server, "_get_pipeline", lambda: _FakePipeline(result))

    code, accepted = _request(gw.base, "/v1/generate", {"prompt": "rc filter"})
    assert code == 202

    body = _poll_terminal(gw.base, accepted["poll_url"])
    assert body["status"] == "done"
    assert body["error"] is None
    comp = body["result"]["circuit"]["components"][0]
    assert (comp["x"], comp["y"]) == (12, 34)


def test_killswitch_refusal_is_status_failed(gw, monkeypatch):
    blocked = SimpleNamespace(ok=False, circuit=None,
                              user_message="I could not produce a verified design for this request.")
    monkeypatch.setattr(server, "_get_pipeline", lambda: _FakePipeline(blocked))

    _, accepted = _request(gw.base, "/v1/generate", {"prompt": "impossible circuit"})
    body = _poll_terminal(gw.base, accepted["poll_url"])

    # The exact string matters: the frontend only terminates on "failed".
    assert body["status"] == "failed"
    assert body["stage"] is None
    assert body["error"]["code"] == "blocked_by_verification"
    assert "verified design" in body["error"]["message"]


def test_pipeline_exception_is_status_failed(gw, monkeypatch):
    monkeypatch.setattr(server, "_get_pipeline",
                        lambda: _FakePipeline(RuntimeError("model file vanished")))

    _, accepted = _request(gw.base, "/v1/generate", {"prompt": "rc filter"})
    body = _poll_terminal(gw.base, accepted["poll_url"])

    assert body["status"] == "failed"
    assert body["error"]["code"] == "pipeline_error"
    assert "model file vanished" in body["error"]["message"]


def test_progress_resets_when_leaving_generate(gw, monkeypatch):
    """Regression: progress/eta describe token decode only. The decode callback
    caps progress at 0.99, so once Generate ends it must not stay pinned there
    through Verify - the UI read a stuck 0.99 as "99%" for the whole check phase.
    """
    at_verify = threading.Event()
    release = threading.Event()

    class _HoldingPipeline:
        def __init__(self):
            self.on_stage = None
            self.generator = SimpleNamespace(progress_cb=None)

        def run(self, prompt):
            self.on_stage("t5", 1)
            self.on_stage("generate", 1)
            self.generator.progress_cb(0.99)  # decode climbs to the cap
            self.on_stage("verify", 1)
            at_verify.set()                    # hold in Verify so the test can poll
            release.wait(timeout=5)
            return SimpleNamespace(ok=True, circuit=_CIRCUIT, user_message="")

    monkeypatch.setattr(server, "_get_pipeline", lambda: _HoldingPipeline())
    _, accepted = _request(gw.base, "/v1/generate", {"prompt": "rc filter"})

    assert at_verify.wait(timeout=5)
    code, body = _request(gw.base, accepted["poll_url"])
    assert code == 200
    assert body["stage"] == "verify"
    assert body["progress"] == 0.0  # cleared, not pinned at the 0.99 decode cap
    assert body["eta_s"] is None

    release.set()
    assert _poll_terminal(gw.base, accepted["poll_url"])["status"] == "done"


def test_second_gateway_on_same_port_fails_loudly(gw):
    with pytest.raises(OSError):
        server.GatewayServer(("127.0.0.1", gw.srv.server_address[1]), server.Handler)
