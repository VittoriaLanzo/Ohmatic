"""RAM guard sizing across platforms and tiers.

_total_ram_mb reads total physical RAM (not momentary free RAM) so a machine the
doctor already sized for a tier is not refused just because a browser is open. The
guard then applies only to GGUF CPU inference, where the mmap'd weights occupy
system RAM; GPU/HF tiers keep weights in VRAM and are skipped.

The Linux and macOS branches are mocked here so CI covers them on any host; the
win32 ctypes branch runs for real when the suite runs on Windows.
"""
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SERVER_PATH = Path(__file__).resolve().parents[1] / "gateway" / "stub" / "server.py"
_spec = importlib.util.spec_from_file_location("gateway_stub_server_ram", _SERVER_PATH)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


# ── _total_ram_mb: one branch per OS ──────────────────────────────────────────

def test_total_ram_mb_linux(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "linux")
    meminfo = "MemTotal:        8017136 kB\nMemFree:          100000 kB\n"
    real_open = open

    def fake_open(path, *args, **kwargs):
        if str(path) == "/proc/meminfo":
            return io.StringIO(meminfo)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    assert server._total_ram_mb() == 8017136 // 1024  # 7829


def test_total_ram_mb_darwin(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(stdout="17179869184\n"),  # 16 GiB
    )
    assert server._total_ram_mb() == 17179869184 // (1024 * 1024)  # 16384


@pytest.mark.skipif(sys.platform != "win32", reason="win32 ctypes branch")
def test_total_ram_mb_win32_real():
    total = server._total_ram_mb()
    assert isinstance(total, int) and total > 1000  # a real machine has > 1 GB


def test_total_ram_mb_unknown_platform_returns_none(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "sunos5")
    assert server._total_ram_mb() is None  # unknown -> guard skipped, fails open


# ── _ram_guard: skip / refuse / pass ──────────────────────────────────────────

def _manifest(tmp_path, tier, model_path):
    m = tmp_path / "active.json"
    m.write_text(json.dumps({"tier": tier, "model_path": str(model_path)}))
    return m


def _gguf(tmp_path, mb):
    f = tmp_path / "model.gguf"
    f.write_bytes(b"\0" * (mb * 1024 * 1024))
    return f


def test_guard_skips_non_gguf_tier(monkeypatch, tmp_path):
    """A bf16 snapshot dir must not be statted and refused: GPU/HF tiers own VRAM."""
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    monkeypatch.setattr(server, "_PIPELINE", None)
    monkeypatch.setattr(server, "_total_ram_mb", lambda: 1024)  # tiny on purpose
    monkeypatch.setattr(server, "_MANIFEST", _manifest(tmp_path, "bf16", snapshot))
    assert server._ram_guard() is None


def test_guard_refuses_when_total_ram_too_small(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE", None)
    monkeypatch.setattr(server, "_MANIFEST",
                        _manifest(tmp_path, "q4_k_m_cpu", _gguf(tmp_path, 5)))
    monkeypatch.setattr(server, "_total_ram_mb", lambda: 4000)  # need=2053, reserve=2048
    msg = server._ram_guard()
    assert msg and "total RAM" in msg and "q4_k_m_cpu" in msg


def test_guard_passes_when_total_ram_ample(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE", None)
    monkeypatch.setattr(server, "_MANIFEST",
                        _manifest(tmp_path, "q4_k_m_cpu", _gguf(tmp_path, 5)))
    monkeypatch.setattr(server, "_total_ram_mb", lambda: 16384)
    assert server._ram_guard() is None


def test_guard_skips_when_pipeline_already_loaded(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE", object())  # loaded model needs no budget
    monkeypatch.setattr(server, "_total_ram_mb", lambda: 1)
    assert server._ram_guard() is None


def test_guard_skips_when_ram_unknown(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE", None)
    monkeypatch.setattr(server, "_total_ram_mb", lambda: None)
    assert server._ram_guard() is None  # unknown RAM -> fail open, never block
