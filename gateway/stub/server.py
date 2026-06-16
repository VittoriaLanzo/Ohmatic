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

# BOM layer: deterministic local parts_list plus the disclosed procurement surface
# (supplier link-outs + the credential-gated Jameco preflight). These are pure-Python
# (stdlib only), so the imports never gate gateway startup the way the ERC stack can.
from shared.parts_list import build_parts_list
from shared.procurement import build_jameco_preflight_response, build_procurement_http_response

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
_JOB_LOCK = threading.Lock()  # llama-cpp is not thread-safe: one generation at a time


def _real_available() -> bool:
    return _MANIFEST.exists()


def _total_ram_mb() -> int | None:
    """Total physical RAM in MB; None = unknown (guard skipped).

    The guard sizes against TOTAL (not momentary free) RAM on purpose: the GGUF
    weights are mmap'd, so the OS pages them in on demand and backs them with the
    file - they never all need to be resident at once, and they are evictable
    rather than charged to the commit/pagefile. Gating on free RAM made a 16 GB
    machine refuse whenever a browser happened to be open. Total RAM is also the
    basis hw_assess used to pick this tier in the first place (ohmatic:374)."""
    try:
        if sys.platform.startswith("linux"):
            for line in open("/proc/meminfo", encoding="utf-8"):
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) // 1024
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                 capture_output=True, text=True, timeout=2)
            return int(out.stdout.strip()) // (1024 * 1024)
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
            return int(st.ullTotalPhys) // (1024 * 1024)
    except Exception:
        pass
    return None


# Headroom over the weights for the KV cache (n_ctx=16384 ~ 2.3 GB for Qwen3-8B
# GQA), compute buffers, and the prefix RAM cache. These are the anonymous, truly
# committed allocations; the weights themselves are file-backed and evictable, so
# counting the full weights file below already builds in a large hidden cushion.
_RAM_HEADROOM_MB = 2048
# Left free for the OS and other apps. Only the headroom above is hard-committed,
# so a 2 GB reserve keeps the machine responsive without refusing on a machine the
# doctor already deemed big enough (it only recommends a CPU tier at >=12 GB).
_RAM_OS_RESERVE_MB = 2048


def _ram_guard() -> str | None:
    """Refusal message only when this machine is genuinely too small for the
    installed tier - sized against TOTAL physical RAM, not momentary free RAM.

    A failed allocation does not crash the process: llama.cpp raises, _run_real_job
    catches it, and the user gets a friendly 'pipeline_error'. This guard is the
    earlier, clearer signal for a machine that can never fit the tier at all."""
    total = _total_ram_mb()
    if total is None or _PIPELINE is not None:  # loaded model needs no new budget
        return None
    try:
        manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        model_path = manifest["model_path"]
    except Exception:
        return None
    # The gate only applies to GGUF CPU inference, where the mmap'd weights occupy
    # system RAM. GPU/HF tiers (bf16 snapshot dir, merged vLLM dir) keep weights in
    # VRAM and manage their own budget, so skip them outright rather than stat a
    # directory and gate on a meaningless size.
    if not str(model_path).endswith(".gguf"):
        return None
    try:
        weights_mb = Path(model_path).stat().st_size // (1024 * 1024)
    except OSError:
        return None
    tier = manifest.get("tier", "installed")
    need_mb = weights_mb + _RAM_HEADROOM_MB
    if total - _RAM_OS_RESERVE_MB < need_mb:
        return (f"This machine has ~{total} MB total RAM, but the '{tier}' tier needs "
                f"~{need_mb} MB plus an OS reserve. Re-run ./ohmatic doctor and fetch "
                f"the recommended tier, or use stub/cloud mode.")
    return None


def _get_pipeline():
    global _PIPELINE
    with _PIPELINE_LOCK:
        if _PIPELINE is None:
            manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
            from inference.pipeline import OhmaticPipeline, PipelineConfig
            cfg = PipelineConfig(t5_model_id=manifest.get("t5_path") or "",
                                 qwen_model_id=manifest["model_path"],
                                 qwen_tokenizer_dir=manifest.get("tokenizer_path") or "")
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


# Demo mode: three ERC-verified example circuits served instantly (no model), keyed
# by their example-prompt text and by the aliases "example 1/2/3". The circuits are
# the dataset's own verified examples, so the demo renders exactly what ships.
_DEMO_TITLES = [
    "555 Timer Astable Oscillator",
    "Single-Supply Audio Amplifier",
    "Precision Half-Wave Rectifier",
]
_DEMO_PROMPTS = {
    "555 timer astable oscillator, 1 Hz LED blink, 5 V supply": _DEMO_TITLES[0],
    "Single-supply audio amplifier, op-amp gain stage, 5 V": _DEMO_TITLES[1],
    "Precision half-wave rectifier, op-amp, ±15 V": _DEMO_TITLES[2],
}
_DEMO_CACHE: dict | None = None


def _demo_examples() -> dict:
    """Title -> flat circuit, loaded once from the checked-in example set."""
    global _DEMO_CACHE
    if _DEMO_CACHE is None:
        path = Path(_ROOT) / "dataset" / "examples.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        _DEMO_CACHE = {c["metadata"]["title"]: c for c in data}
    return _DEMO_CACHE


def _demo_circuit(prompt: str) -> dict | None:
    """The canned circuit for an example prompt or an 'example N' alias, else None."""
    text = prompt.strip()
    title = _DEMO_PROMPTS.get(text)
    if title is None:
        m = re.fullmatch(r"example\s*([123])", text, re.IGNORECASE)
        if m:
            title = _DEMO_TITLES[int(m.group(1)) - 1]
    if title is None:
        return None
    try:
        return _demo_examples().get(title)
    except Exception:
        return None


def _parts_list_for(circuit_flat: dict) -> tuple[list, int]:
    """Deterministic local parts_list for a verified circuit, plus its build time in ms.
    Never fails a finished job: an unknown component type or a missing registry yields an
    empty list, and the UI falls back to circuit-derived rows."""
    started = time.time()
    try:
        rows = build_parts_list(circuit_flat)
    except Exception:
        return [], 0
    return rows, int((time.time() - started) * 1000)


def _run_real_job(job_id: str, prompt: str) -> None:
    t0 = time.time()
    try:
        # stage stays "queued" while another generation holds the model
        with _JOB_LOCK:
            JOBS[job_id]["t0"] = time.time()  # ETA clock starts when WE start
            JOBS[job_id]["stage"] = "t5"
            pipe = _get_pipeline()
            def _stage(stage, attempt, _j=job_id):
                j = JOBS[_j]
                j["stage"] = stage
                j["loops"] = max(j.get("loops", 0), attempt - 1)
                if stage == "generate":  # rate clock restarts per attempt: retries are
                    j.pop("decode_t0", None)  # ~90% prompt-lookup hits, much faster
                else:
                    # progress/eta describe token decode only. The cb caps progress
                    # at 0.99, so without this it stays pinned there through Verify
                    # and reads as "stuck at 99%". Clear it so the API reports decode
                    # progress only while decoding; the frontend's high-water bar
                    # guard keeps the rail from rewinding when a retry re-enters generate.
                    j["progress"] = 0.0
                    j.pop("eta_s", None)
                    j.pop("decode_t0", None)
            pipe.on_stage = _stage
            gen = getattr(pipe, "generator", None)
            if gen is not None and hasattr(gen, "progress_cb"):
                def _cb(frac, _j=job_id):  # frac is monotonic within an attempt; cross-stage
                    j = JOBS[_j]           # bar monotonicity is the frontend's job now
                    j.setdefault("decode_t0", time.time())
                    j["progress"] = max(j.get("progress", 0.0), frac)
                    if frac > 0.02:  # same-speed extrapolation on THIS attempt's rate
                        j["eta_s"] = int((time.time() - j["decode_t0"]) * (1 - frac) / frac)
                gen.progress_cb = _cb
            result = pipe.run(prompt)
        if result.ok:
            circuit_flat = _flatten(result.circuit)
            parts_list, parts_ms = _parts_list_for(circuit_flat)
            JOBS[job_id].update(status="done", stage=None, result={
                "circuit": circuit_flat,
                "drc_warnings": [],
                "bom": [],
                "parts_list": parts_list,
                "latency_ms": {"inference": int((time.time() - t0) * 1000), "drc": 0,
                               "bom": 0, "parts_list": parts_ms},
            })
        else:
            # Contract (shared/docs/contracts.md): terminal failure is "failed".
            # Anything else keeps the frontend polling forever on a finished job.
            JOBS[job_id].update(status="failed", stage=None, error={
                "code": "blocked_by_verification",
                "message": result.user_message or "Verification did not pass. Nothing was delivered.",
            })
    except Exception as exc:
        JOBS[job_id].update(status="failed", stage=None,
                            error={"code": "pipeline_error", "message": str(exc)[:300]})
import socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

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

    def _read_json_or_error(self):
        """Read and parse a JSON request body. On any problem, send the matching error
        response and return None; otherwise return the parsed value."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_json(400, {"error": "invalid Content-Length header"})
            return None
        if content_length < 0:
            self.send_json(400, {"error": "invalid Content-Length header"})
            return None
        if content_length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "request body too large"})
            return None
        raw = self.rfile.read(content_length)
        if not raw:
            self.send_json(400, {"error": "request body is required"})
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid JSON body"})
            return None

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
        if path == "/v1/procurement/matches":
            # BOM procurement: a deterministic parts_list maps to disclosed supplier
            # link-outs. Jameco lookups stay credential-gated and inert until configured;
            # build_procurement_http_response owns all validation and the status codes.
            payload = self._read_json_or_error()
            if payload is None:
                return
            status, body = build_procurement_http_response(payload)
            self.send_json(status, body)
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
            # Demo mode: a canned, ERC-verified example renders instantly, no model
            # required (works even with no weights installed).
            demo = _demo_circuit(prompt)
            if demo is not None:
                job_id = uuid.uuid4().hex[:12]
                parts_list, parts_ms = _parts_list_for(demo)
                JOBS[job_id] = {
                    "status": "done", "stage": None, "t0": time.time(),
                    "progress": 1.0, "loops": 0, "error": None,
                    "result": {"circuit": demo, "drc_warnings": [], "bom": [],
                               "parts_list": parts_list,
                               "latency_ms": {"inference": 0, "drc": 0, "bom": 0, "parts_list": parts_ms}},
                }
                self.send_json(202, {"job_id": job_id, "poll_url": f"/v1/jobs/{job_id}/status"})
                return
            if _real_available():
                guard = _ram_guard()
                if guard:
                    self.send_json(503, {"error": "insufficient_memory", "message": guard})
                    return
                job_id = uuid.uuid4().hex[:12]
                JOBS[job_id] = {"status": "running", "stage": "queued", "t0": time.time(),
                                "progress": 0.0, "loops": 0, "result": None, "error": None}
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
                                     "progress": j.get("progress"), "loops": j.get("loops", 0),
                                     "eta_s": j.get("eta_s"),
                                     "elapsed_s": int(time.time() - j["t0"]) if "t0" in j else None,
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
                if doc["mode"] == "real":
                    try:
                        m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
                        doc["installed"] = {"tier": m.get("tier", ""),
                                            "name": Path(m.get("model_path", "")).stem}
                    except Exception:
                        pass
                self.send_json(200, doc)
            except Exception:
                self.send_json(200, {"recommended_model": "stub", "mode": "stub",
                                     "reason": "doctor has not run yet - start via ./ohmatic start"})
        elif path == "/v1/procurement/suppliers/jameco/preflight":
            # Setup readiness only: reads env, makes no network call, redacts secrets.
            self.send_json(200, build_jameco_preflight_response())
        elif path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})


class GatewayServer(ThreadingHTTPServer):
    """One thread per request so a slow client can never block the poll loop.
    Generation itself stays serialized by _JOB_LOCK."""
    daemon_threads = True
    # Windows SO_REUSEADDR lets a SECOND gateway silently double-bind the port,
    # splitting jobs across two processes (poll sees "queued"/404 forever).
    # Exclusive bind turns that into a loud startup failure instead.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__ == "__main__":
    import os
    port = int(os.environ.get("OHMATIC_PORT", "8080"))
    try:
        srv = GatewayServer(("0.0.0.0", port), Handler)
    except OSError:
        print(f"Port {port} is already in use - another gateway is running. "
              f"Run ./ohmatic stop, then start again.", file=sys.stderr)
        sys.exit(1)
    print(f"Gateway listening on :{port}")
    srv.serve_forever()
