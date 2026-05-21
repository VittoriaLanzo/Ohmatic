#!/usr/bin/env python3
"""Stub server for inference. Returns hardcoded valid responses. Replace with production implementation in Stage 1. See shared/docs/contracts.md for the contract."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

HARDCODED_CIRCUIT = {
    "metadata": {
        "title": "Stub Inference Circuit",
        "description": "Hardcoded inference stub response",
        "version": "0.1",
        "tags": ["stub", "inference"]
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
        if self.path == "/infer":
            content_length = int(self.headers.get("Content-Length", 0))
            _ = self.rfile.read(content_length)  # consume body
            self.send_json(200, {
                "circuit": HARDCODED_CIRCUIT,
                "raw_tokens": 512,
                "duration_ms": 0
            })
        else:
            self.send_json(404, {"error": "not_found"})

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    print("Inference stub listening on :8001")
    HTTPServer(("0.0.0.0", 8001), Handler).serve_forever()
