#!/usr/bin/env python3
"""Combined static + mock API server for Ohmatic frontend demo."""
import json
import re
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

DIST = Path(__file__).parent / "dist"
ROOT = Path(__file__).resolve().parents[1]

from shared.parts_list import build_parts_list

HARDCODED_CIRCUIT = {
    "metadata": {
        "title": "Stub Circuit",
        "description": "Hardcoded stub",
        "version": "0.1",
        "tags": ["stub"],
    },
    "components": [
        {"id": "R1", "type": "resistor", "value": "10kΩ", "part": "0603",
         "x": 50, "y": 50, "pins": {"1": "1", "2": "2"}},
        {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
         "x": 10, "y": 10, "pins": {"1": "1"}},
        {"id": "GND1", "type": "power_gnd", "value": "", "part": "GND",
         "x": 90, "y": 90, "pins": {"1": "1"}},
    ],
    "nets": [
        {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
        {"name": "GND", "pins": ["R1.2", "GND1.1"]},
    ],
}


def build_done_result(circuit):
    parts_list = build_parts_list(circuit)
    return {
        "circuit": circuit,
        "drc_warnings": [],
        "parts_list": parts_list,
        "latency_ms": {"inference": 0, "drc": 0, "parts_list": 0},
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/v1/generate":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "invalid JSON"})
                return
            prompt = body.get("prompt", "").strip()
            if not prompt:
                self.send_json(400, {"error": "prompt must not be empty"})
                return
            self.send_json(202, {
                "job_id": "stub-job-01",
                "poll_url": "/v1/jobs/stub-job-01/status",
            })
        else:
            self.send_json(404, {"error": "not_found"})

    def do_GET(self):
        path = self.path.split("?")[0]
        m = re.fullmatch(r"/v1/jobs/([^/]+)/status", path)
        if m:
            job_id = m.group(1)
            if job_id != "stub-job-01":
                self.send_json(404, {"error": "job_not_found"})
                return
            self.send_json(200, {
                "status": "done",
                "stage": None,
                "result": build_done_result(HARDCODED_CIRCUIT),
                "error": None,
            })
        elif path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            # SPA fallback: unknown paths serve index.html
            if not path.startswith("/assets/") and "." not in path.split("/")[-1]:
                self.path = "/index.html"
            super().do_GET()


if __name__ == "__main__":
    port = 5173
    print(f"Ohmatic dev server (mock) -> http://localhost:{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
