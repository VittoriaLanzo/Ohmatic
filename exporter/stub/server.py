#!/usr/bin/env python3
"""Exporter service: turns an OhmaticCircuitV01 into downloadable KiCad files.

This is a first-class Ohmatic service, not a hardcoded stub - the emitters under
exporter/emit/ are the real implementation. It is the one service that binds
loopback-only (127.0.0.1) instead of 0.0.0.0, because it is also the license
firewall: if a future format shells out to GPL `kicad-cli`, that heavy, copyleft
dependency stays isolated behind this process boundary. See shared/docs/contracts.md
section 10 for the contract.

Handshake (local-first, mTLS-ready):
  - loopback bind + Host/Origin pinned to localhost  -> blocks DNS-rebinding / CSRF
  - optional bearer token (OHMATIC_EXPORT_TOKEN)      -> per-session auth from launcher
  - optional TLS / mutual TLS via _build_httpd()      -> drop-in when run beyond loopback
Plain HTTP on loopback is the default on purpose: browsers already treat
http://127.0.0.1 as a secure context, so TLS there is ceremony. The seam below turns
it on without touching any route code the day Ohmatic is exposed off the machine.
"""
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Launcher runs this with cwd=exporter/stub; make the repo root importable so the
# emitters (the single source of truth for KiCad output) resolve.
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from exporter.emit import SCHEMA_VERSIONS, build_export, capabilities

MAX_BODY_BYTES = 4 * 1024 * 1024  # circuits are small; generous ceiling, hard cap
_LOCAL_HOSTS = {"127.0.0.1", "localhost", ""}


class Handler(BaseHTTPRequestHandler):
    timeout = 30

    def log_message(self, format, *args):
        pass

    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handshake_error(self):
        """None if the request may proceed, else (status, body) to return.

        Pins Host/Origin to localhost and (when OHMATIC_EXPORT_TOKEN is set) checks a
        constant-time bearer token. /health skips this - it is an unauthenticated
        liveness probe per the contract.
        """
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in _LOCAL_HOSTS:
            return 421, {"error": "bad_host"}
        origin = self.headers.get("Origin")
        if origin is not None and urlparse(origin).hostname not in _LOCAL_HOSTS:
            return 403, {"error": "cross_origin_blocked"}
        token = os.environ.get("OHMATIC_EXPORT_TOKEN")
        if token:
            auth = self.headers.get("Authorization", "")
            presented = auth[7:] if auth.startswith("Bearer ") else ""
            if not hmac.compare_digest(presented, token):
                return 401, {"error": "unauthorized"}
        return None

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_json(400, {"error": "invalid Content-Length header"})
            return None
        if length < 0:
            self.send_json(400, {"error": "invalid Content-Length header"})
            return None
        if length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "request body too large"})
            return None
        raw = self.rfile.read(length)
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
        denied = self._handshake_error()
        if denied:
            self.send_json(*denied)
            return
        if path != "/v1/export":
            self.send_json(404, {"error": "not_found"})
            return
        body = self._read_json()
        if body is None:
            return
        if not isinstance(body, dict):
            self.send_json(400, {"error": "request body must be a JSON object"})
            return
        circuit = body.get("circuit")
        if not isinstance(circuit, dict):
            self.send_json(400, {"error": "missing 'circuit' field"})
            return
        for key in ("metadata", "components", "nets"):
            if not circuit.get(key):
                self.send_json(422, {"error": f"circuit missing '{key}'"})
                return
        version = (circuit.get("metadata") or {}).get("version")
        if version not in SCHEMA_VERSIONS:
            self.send_json(422, {
                "error": "unsupported_schema_version",
                "message": f'metadata.version "{version}" is not supported',
            })
            return
        fmt = body.get("format", "netlist")
        try:
            result = build_export(circuit, fmt)
        except ValueError:
            self.send_json(400, {"error": f"unsupported format: {fmt!r}"})
            return
        self.send_json(200, result)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        denied = self._handshake_error()
        if denied:
            self.send_json(*denied)
            return
        if path == "/v1/export/capabilities":
            self.send_json(200, capabilities())
            return
        self.send_json(404, {"error": "not_found"})


def _build_httpd(port: int) -> ThreadingHTTPServer:
    """Loopback HTTP by default; TLS / mutual TLS when certs are configured.

    Set OHMATIC_EXPORT_TLS_CERT + _KEY to serve HTTPS. Add _CLIENT_CA to additionally
    require and verify a client certificate (mutual TLS). This is the whole seam: no
    route code changes, and loopback dev keeps working untouched when these are unset.
    """
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    cert = os.environ.get("OHMATIC_EXPORT_TLS_CERT")
    key = os.environ.get("OHMATIC_EXPORT_TLS_KEY")
    if cert and key:
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        client_ca = os.environ.get("OHMATIC_EXPORT_TLS_CLIENT_CA")
        if client_ca:
            ctx.load_verify_locations(client_ca)
            ctx.verify_mode = ssl.CERT_REQUIRED  # mutual TLS
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    return httpd


class _ExporterServer(ThreadingHTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    port = int(os.environ.get("OHMATIC_PORT", "8004"))
    scheme = "https" if os.environ.get("OHMATIC_EXPORT_TLS_CERT") else "http"
    print(f"Exporter listening on {scheme}://127.0.0.1:{port}")
    _build_httpd(port).serve_forever()
