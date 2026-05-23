#!/usr/bin/env python3
"""Stub server for verifier. Returns hardcoded valid responses. Replace with production implementation in Stage 1. See shared/docs/contracts.md for the contract."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

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
        if path == "/verify":
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
            # Minimal Tier-1 structural check so the 422 path is exercised by integration tests.
            # Stage 0: only checks key presence and null values; full Tier 1/2/3 DRC deferred to Stage 1.
            missing = [k for k in ("metadata", "components", "nets")
                       if k not in circuit or circuit[k] is None]
            if missing:
                self.send_json(422, {
                    "errors": [f"missing required field: {k}" for k in missing],
                    "warnings": []
                })
                return
            self.send_json(200, {
                "circuit": circuit,
                "warnings": [],
                "errors": []
            })
        else:
            self.send_json(404, {"error": "not_found"})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    print("Verifier stub listening on :8002")
    HTTPServer(("0.0.0.0", 8002), Handler).serve_forever()
