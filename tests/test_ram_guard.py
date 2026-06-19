"""RAM guard sizing across platforms and tiers.

_total_ram_mb reads total physical RAM (not momentary free RAM) so a machine the
doctor already sized for a tier is not refused just because a browser is open. The
guard then applies only to GGUF CPU inference; GPU/HF tiers keep weights in VRAM
and are skipped.

The cost model estimates the TRUE committed peak - weights + KV(n_ctx) + prefix
cache - against total RAM minus an OS reserve, instead of the old
weights-plus-fixed-headroom gate that charged the evictable mmap weights and
ignored the committed allocations that cause OOM. T5 is not charged: it runs in a
short-lived subprocess that exits before generation, so it never sets the peak.

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

def _manifest(tmp_path, tier, model_path, t5_path=None):
    m = tmp_path / "active.json"
    payload = {"tier": tier, "model_path": str(model_path)}
    if t5_path is not None:
        payload["t5_path"] = str(t5_path)
    m.write_text(json.dumps(payload))
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


# New cost model: committed peak ~= weights + KV(n_ctx) + prefix cache, checked
# against total RAM minus the OS reserve. For a 5 MB stand-in gguf with n_ctx=16384:
#   KV   = 147456 B/token * 16384 // 1MiB = 2304 MB
#   need = weights(5) + KV(2304) + prefix(2048) = 4357 MB
# so a machine refuses when total - 2048 (OS reserve) < 4357, i.e. total < 6405 MB.

def test_guard_refuses_when_total_ram_too_small(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE", None)
    monkeypatch.setattr(server, "_MANIFEST",
                        _manifest(tmp_path, "q4_k_m_cpu", _gguf(tmp_path, 5)))
    # 6000 - 2048 (OS reserve) = 3952 < 4357 (need) -> refuse. The OLD gate (weights
    # + 2048 headroom = ~2053) would have PASSED this machine and then OOM'd, because
    # it charged the evictable mmap weights and ignored the committed KV/prefix cache.
    monkeypatch.setattr(server, "_total_ram_mb", lambda: 6000)
    msg = server._ram_guard()
    assert msg and "total RAM" in msg and "q4_k_m_cpu" in msg
    assert "KV" in msg and "prefix cache" in msg  # message names the committed terms


def test_guard_passes_when_total_ram_ample(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_PIPELINE", None)
    monkeypatch.setattr(server, "_MANIFEST",
                        _manifest(tmp_path, "q4_k_m_cpu", _gguf(tmp_path, 5)))
    monkeypatch.setattr(server, "_total_ram_mb", lambda: 16384)  # 16384-2048=14336 >= 4357
    assert server._ram_guard() is None


def test_guard_does_not_charge_t5_when_subprocess_isolated(monkeypatch, tmp_path):
    """T5 runs in a short-lived subprocess (inference/t5_subprocess.py) that exits
    before generation, so a t5_path in the manifest must NOT change the verdict: the
    committed peak is weights + KV + prefix cache either way."""
    # need = 5 + 2304 + 2048 = 4357 regardless of t5_path. total 8000 -> 8000-2048 =
    # 5952 >= 4357, so both manifests pass; t5_path adds nothing to the committed peak.
    monkeypatch.setattr(server, "_PIPELINE", None)
    monkeypatch.setattr(server, "_total_ram_mb", lambda: 8000)

    monkeypatch.setattr(server, "_MANIFEST",
                        _manifest(tmp_path, "q4_k_m_cpu", _gguf(tmp_path, 5)))
    assert server._ram_guard() is None  # no t5_path

    monkeypatch.setattr(
        server, "_MANIFEST",
        _manifest(tmp_path, "q4_k_m_cpu", _gguf(tmp_path, 5), t5_path=tmp_path / "t5"))
    assert server._ram_guard() is None  # t5_path present -> still passes (subprocess T5)


# ── _n_gpu_layers_for: tier mapping + env override ────────────────────────────

def test_n_gpu_layers_cpu_tier_keeps_layers_in_ram(monkeypatch):
    monkeypatch.delenv("OHMATIC_N_GPU_LAYERS", raising=False)
    assert server._n_gpu_layers_for("q4_k_m_cpu") == 0


def test_n_gpu_layers_gpu_tiers_offload_all(monkeypatch):
    monkeypatch.delenv("OHMATIC_N_GPU_LAYERS", raising=False)
    assert server._n_gpu_layers_for("q4_k_m") == -1
    assert server._n_gpu_layers_for("q8_0") == -1


def test_n_gpu_layers_env_override_partial_offload(monkeypatch):
    monkeypatch.setenv("OHMATIC_N_GPU_LAYERS", "12")
    assert server._n_gpu_layers_for("q4_k_m_cpu") == 12  # override beats the _cpu default
    assert server._n_gpu_layers_for("q4_k_m") == 12


def test_n_gpu_layers_malformed_override_falls_back_to_tier(monkeypatch):
    monkeypatch.setenv("OHMATIC_N_GPU_LAYERS", "all-of-them")
    assert server._n_gpu_layers_for("q4_k_m_cpu") == 0  # malformed -> tier default


def test_guard_skips_when_pipeline_already_loaded(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE", object())  # loaded model needs no budget
    monkeypatch.setattr(server, "_total_ram_mb", lambda: 1)
    assert server._ram_guard() is None


def test_guard_skips_when_ram_unknown(monkeypatch):
    monkeypatch.setattr(server, "_PIPELINE", None)
    monkeypatch.setattr(server, "_total_ram_mb", lambda: None)
    assert server._ram_guard() is None  # unknown RAM -> fail open, never block
