#!/usr/bin/env python3
"""Stub server for gateway. Returns hardcoded valid responses. Replace with production implementation in Stage 1. See shared/docs/contracts.md for the contract."""
import json
import re
import sys
from pathlib import Path

# Runtime entry point: the launcher runs this with cwd=gateway/stub, so the
# repo root must be importable for the ERC/prompt single sources of truth.
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from eval.diagnostics import analyze_schematic as _analyze_schematic
    from shared.erc_feedback import format_erc_errors as _format_erc_errors
    from shared.prompt_builder import build_system_prompt as _build_system_prompt
    VERIFY_AVAILABLE = True
except Exception:
    VERIFY_AVAILABLE = False

# Real-model mode: when ./ohmatic fetch has installed weights, /v1/generate runs
# the actual pipeline (T5 -> GGUF via llama.cpp -> ERC -> killswitch) in a
# worker thread; the stub circuit is only the no-weights fallback.
import threading
import time
import uuid

_MANIFEST = Path(_ROOT) / "models" / "active.json"
JOBS: dict = {}
_PIPELINE = None
_PIPELINE_LOCK = threading.Lock()


def _real_available() -> bool:
    return _MANIFEST.exists()


def _available_ram_mb() -> int | None:
    """Best effort; None = unknown (guard skipped)."""
    try:
        if sys.platform.startswith("linux"):
            for line in open("/proc/meminfo", encoding="utf-8"):
                if line.startswith("MemAvailable"):
                    return int(line.split()[1]) // 1024
        if sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX(); st.dwLength = ctypes.sizeof(st)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return int(st.ullAvailPhys) // (1024 * 1024)
    except Exception:
        pass
    return None


def _ram_guard() -> str | None:
    """Refusal message when the model + headroom cannot fit in available RAM."""
    avail = _available_ram_mb()
    if avail is None or _PIPELINE is not None:  # loaded model needs no new budget
        return None
    try:
        need = json.loads(_MANIFEST.read_text(encoding="utf-8"))["model_path"]
        need_mb = Path(need).stat().st_size // (1024 * 1024) + 2048  # weights + ctx headroom
    except Exception:
        return None
    if avail < need_mb:
        return (f"Not enough free RAM to load the model safely: need ~{need_mb} MB, "
                f"{avail} MB available. Close applications or fetch a smaller tier "
                f"(./ohmatic fetch --tier q4_k_m_cpu).")
    return None


def _get_pipeline():
    global _PIPELINE
    with _PIPELINE_LOCK:
        if _PIPELINE is None:
            manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
            from inference.pipeline import OhmaticPipeline, PipelineConfig
            cfg = PipelineConfig(t5_model_id=manifest.get("t5_path") or "",
                                 qwen_model_id=manifest["model_path"])
            _PIPELINE = OhmaticPipeline.from_config(cfg)
        return _PIPELINE


def _flatten(circuit: dict) -> dict:
    """Two-stage circuit JSON -> the flat shape the UI renders."""
    topo = circuit.get("STAGE_1_TOPOLOGY", circuit)
    pos = {n.get("id"): n for n in circuit.get("STAGE_2_LAYOUT", {}).get("spatial_nodes", [])}
    comps = [{**c, "x": pos.get(c.get("id"), {}).get("x", 0),
              "y": pos.get(c.get("id"), {}).get("y", 0)}
             for c in topo.get("components", [])]
    return {"metadata": circuit.get("metadata", {}), "components": comps,
            "nets": topo.get("nets", [])}


def _run_real_job(job_id: str, prompt: str) -> None:
    t0 = time.time()
    try:
        JOBS[job_id]["stage"] = "inference"
        pipe = _get_pipeline()
        gen = getattr(pipe, "generator", None)
        if gen is not None and hasattr(gen, "progress_cb"):
            def _cb(frac, _j=job_id):  # monotonic: retries never move the bar backward
                JOBS[_j]["progress"] = max(JOBS[_j].get("progress", 0.0), frac)
            gen.progress_cb = _cb
        result = pipe.run(prompt)
        if result.ok:
            JOBS[job_id].update(status="done", stage=None, result={
                "circuit": _flatten(result.circuit),
                "drc_warnings": [],
                "bom": [],
                "latency_ms": {"inference": int((time.time() - t0) * 1000), "drc": 0, "bom": 0},
            })
        else:
            JOBS[job_id].update(status="error", stage=None, error={
                "code": "blocked_by_verification",
                "message": result.user_message or "Verification did not pass.",
            })
    except Exception as exc:
        JOBS[job_id].update(status="error", stage=None,
                            error={"code": "pipeline_error", "message": str(exc)[:300]})
from http.server import HTTPServer, BaseHTTPRequestHandler

MAX_BODY_BYTES = 1 * 1024 * 1024

HARDCODED_CIRCUIT = {
    "metadata": {
        "title": "Stub Circuit",
        "description": "Hardcoded stub",
        "version": "0.1",
        "tags": ["stub"]
    },
    "components": [
        {"id": "R1", "type": "resistor", "value": "10kΩ", "part": "0603",
         "x": 50, "y": 50, "pins": {"1": "1", "2": "2"}},
        {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
         "x": 10, "y": 10, "pins": {"1": "1"}},
        {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
         "x": 90, "y": 90, "pins": {"1": "1"}}
    ],
    "nets": [
        {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
        {"name": "GND", "pins": ["R1.2", "GND1.1"]}
    ]
}


class Handler(BaseHTTPRequestHandler):
    timeout = 30  # abort reads that block longer than 30 s

    def log_message(self, format, *args):
        pass  # suppress request logs

    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/v1/verify":
            # ERC-as-a-service for browser-mode generation: the SAME
            # analyze_schematic + feedback format as training/prod/benchmark.
            if not VERIFY_AVAILABLE:
                self.send_json(503, {"error": "erc_unavailable"})
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                circuit = body.get("circuit")
                assert isinstance(circuit, dict)
            except Exception:
                self.send_json(400, {"error": "bad_request",
                                     "detail": "POST {\"circuit\": {...}}"})
                return
            diags = _analyze_schematic(circuit).get("diagnostics", [])
            self.send_json(200, {
                "passed": not diags,
                "diagnostics": diags,
                "feedback": _format_erc_errors(diags) if diags else ""
            })
            return
        if path == "/v1/generate":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self.send_json(400, {"error": "invalid Content-Length header"})
                return
            if content_length < 0:
                self.send_json(400, {"error": "invalid Content-Length header"})
                return
            if content_length > MAX_BODY_BYTES:
                self.send_json(413, {"error": "request body too large"})
                return
            raw = self.rfile.read(content_length)
            if not raw:
                self.send_json(400, {"error": "request body is required"})
                return
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "invalid JSON body"})
                return
            if not isinstance(body, dict):
                self.send_json(400, {"error": "request body must be a JSON object"})
                return
            prompt = body.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                self.send_json(400, {"error": "prompt must not be empty"})
                return
            if "options" in body:
                options_raw = body["options"]
                if not isinstance(options_raw, dict):
                    self.send_json(400, {"error": "options must be a JSON object"})
                    return
                options = options_raw
            else:
                options = {}
            if "temperature" in options:
                temperature = options["temperature"]
                if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
                    self.send_json(400, {"error": "options.temperature must be a number"})
                    return
                if not (0.0 <= temperature <= 1.0):
                    self.send_json(400, {"error": "options.temperature must be in [0, 1]"})
                    return
            if _real_available():
                guard = _ram_guard()
                if guard:
                    self.send_json(503, {"error": "insufficient_memory", "message": guard})
                    return
                job_id = uuid.uuid4().hex[:12]
                JOBS[job_id] = {"status": "running", "stage": "queued",
                                "progress": 0.0, "result": None, "error": None}
                threading.Thread(target=_run_real_job, args=(job_id, prompt),
                                 daemon=True).start()
                self.send_json(202, {"job_id": job_id,
                                     "poll_url": f"/v1/jobs/{job_id}/status"})
            else:
                self.send_json(503, {
                    "error": "model_not_installed",
                    "message": "No model installed. Run ./ohmatic fetch (or ./ohmatic start and accept the pull)."
                })
        else:
            self.send_json(404, {"error": "not_found"})

    def do_GET(self):
        path = self.path.split("?")[0]  # strip query string; BaseHTTPRequestHandler.path includes it
        m = re.fullmatch(r"/v1/jobs/([^/]+)/status", path)
        if m:
            job_id = m.group(1)
            if job_id in JOBS:
                j = JOBS[job_id]
                self.send_json(200, {"status": j["status"], "stage": j["stage"],
                                     "progress": j.get("progress"),
                                     "result": j["result"], "error": j["error"]})
                return
            self.send_json(404, {"error": "job_not_found"})
        elif path == "/v1/system-prompt":
            if not VERIFY_AVAILABLE:
                self.send_json(503, {"error": "prompt_unavailable"})
                return
            self.send_json(200, {"system_prompt": _build_system_prompt()})
        elif path == "/v1/doctor":
            # Hardware verdict written by `ohmatic doctor` / `ohmatic start` (hw_assess).
            import os
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "..", ".ohmatic-run", "doctor.json")
            try:
                with open(p, encoding="utf-8") as fh:
                    doc = json.load(fh)
                doc["mode"] = "real" if _real_available() else "stub"
                self.send_json(200, doc)
            except Exception:
                self.send_json(200, {"recommended_model": "stub", "mode": "stub",
                                     "reason": "doctor has not run yet - start via ./ohmatic start"})
        elif path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("OHMATIC_PORT", "8080"))
    print(f"Gateway stub listening on :{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
