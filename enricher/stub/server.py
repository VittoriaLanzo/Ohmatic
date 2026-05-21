#!/usr/bin/env python3
"""Stub server for enricher. Returns hardcoded valid responses. Replace with production implementation in Stage 1. See shared/docs/contracts.md for the contract."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
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
        if self.path == "/enrich":
            content_length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_length)
            try:
                payload = json.loads(raw)
                components = payload.get("circuit", {}).get("components", [])
                bom = [
                    {
                        "id": c.get("id", "?"),
                        "mpn": None,
                        "description": f"{c.get('type', 'unknown')} {c.get('value', '')}".strip(),
                        "price_usd": None,
                        "url": None,
                        "mpn_found": False
                    }
                    for c in components
                ]
            except (json.JSONDecodeError, KeyError, TypeError):
                bom = []
            self.send_json(200, bom)
        else:
            self.send_json(404, {"error": "not_found"})

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    print("Enricher stub listening on :8003")
    HTTPServer(("0.0.0.0", 8003), Handler).serve_forever()
