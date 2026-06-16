#!/usr/bin/env python3
"""Stub server for enricher. Builds the deterministic local parts list for a verified
circuit via the canonical shared.parts_list builder (the single source of truth, shared
with the gateway). See shared/docs/contracts.md section 6 for the contract."""
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# The launcher runs this with cwd=enricher/stub, so put the repo root on sys.path to
# import the shared parts_list builder. Guarded: a missing repo root (e.g. a narrow
# container mount) degrades /enrich to 503 instead of crashing startup.
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    from shared.parts_list import build_parts_list
    BUILD_AVAILABLE = True
except Exception:
    BUILD_AVAILABLE = False

MAX_BODY_BYTES = 1 * 1024 * 1024


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
        if path == "/enrich":
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
                payload = json.loads(raw)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "invalid JSON body"})
                return
            if not isinstance(payload, dict):
                self.send_json(400, {"error": "request body must be a JSON object"})
                return
            if "circuit" not in payload:
                self.send_json(400, {"error": "missing 'circuit' field"})
                return
            circuit = payload["circuit"]
            if not isinstance(circuit, dict):
                self.send_json(400, {"error": "'circuit' must be an object"})
                return
            if "components" not in circuit:
                self.send_json(400, {"error": "malformed 'circuit' field"})
                return
            components = circuit["components"]
            if not isinstance(components, list):
                self.send_json(400, {"error": "'components' must be a list"})
                return
            if not BUILD_AVAILABLE:
                self.send_json(503, {"error": "enricher_unavailable"})
                return
            try:
                rows = build_parts_list(circuit)
            except ValueError as exc:
                self.send_json(422, {"error": str(exc)})
                return
            self.send_json(200, rows)
        else:
            self.send_json(404, {"error": "not_found"})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("OHMATIC_PORT", "8003"))
    print(f"Enricher stub listening on :{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
