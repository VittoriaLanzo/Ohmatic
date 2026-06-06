#!/usr/bin/env python3
"""Stub server for gateway. Returns hardcoded valid responses. Replace with production implementation in Stage 1. See shared/docs/contracts.md for the contract."""
import json
import re
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
            self.send_json(202, {
                "job_id": "stub-job-01",
                "poll_url": "/v1/jobs/stub-job-01/status"
            })
        else:
            self.send_json(404, {"error": "not_found"})

    def do_GET(self):
        path = self.path.split("?")[0]  # strip query string; BaseHTTPRequestHandler.path includes it
        m = re.fullmatch(r"/v1/jobs/([^/]+)/status", path)
        if m:
            job_id = m.group(1)
            if job_id != "stub-job-01":
                self.send_json(404, {"error": "job_not_found"})
                return
            self.send_json(200, {
                "status": "done",
                "stage": None,
                "result": {
                    "circuit": HARDCODED_CIRCUIT,
                    "drc_warnings": [],
                    "bom": [],
                    "latency_ms": {"inference": 0, "drc": 0, "bom": 0}
                },
                "error": None
            })
        elif path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("OHMATIC_PORT", "8080"))
    print(f"Gateway stub listening on :{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
