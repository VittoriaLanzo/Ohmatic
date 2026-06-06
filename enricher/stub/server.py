#!/usr/bin/env python3
"""Stub server for enricher. Returns hardcoded valid responses. Replace with production implementation in Stage 1. See shared/docs/contracts.md for the contract."""
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
            bom = []
            for c in components:
                if not isinstance(c, dict):
                    continue
                cid = c.get("id")
                if not isinstance(cid, str) or not cid:
                    continue
                bom.append({
                    "id": cid,
                    "mpn": None,
                    "description": f"{c.get('type', 'unknown')} {c.get('value', '')}".strip(),
                    "price_usd": None,
                    "url": None,
                    "mpn_found": False
                })
            self.send_json(200, bom)
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
