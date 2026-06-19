"""SubprocessT5Normalizer: torch-free parent + graceful fallback.

These tests run WITHOUT torch installed (CI has no torch on the edge image). They
cover the parent-side contract only: the worker (which imports torch) is exercised
by replacing the spawned command with a tiny stub, so we never need a real model
or GPU here.
"""
import subprocess
import sys

import pytest

from inference import t5_subprocess
from inference.t5_subprocess import SubprocessT5Normalizer, _OUT_MARKER


def test_module_import_is_torch_free():
    """Importing the parent module must NOT pull torch into the process."""
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules


def _fake_run(returncode=0, stdout="", stderr="", raises=None):
    """Mimic subprocess.run's bytes-mode contract: _spawn passes input as bytes
    and decodes stdout/stderr itself, so the fake returns bytes."""
    out = stdout.encode("utf-8") if isinstance(stdout, str) else stdout
    err = stderr.encode("utf-8") if isinstance(stderr, str) else stderr

    def _run(cmd, input=None, capture_output=None, timeout=None):
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, out, err)
    return _run


def test_normalize_happy_path(monkeypatch):
    """Worker stdout (marker + text) -> stripped, gated normalization."""
    monkeypatch.setattr(
        t5_subprocess.subprocess, "run",
        _fake_run(stdout=_OUT_MARKER + "a 5V regulator"),
    )
    norm = SubprocessT5Normalizer("some/model")
    assert norm.normalize("make me a 5v reg") == "a 5V regulator"


def test_faithfulness_repair_reattaches_dropped_specifics(monkeypatch):
    """Dropped user specific (AMS1117) is re-attached by the repair gate, exactly
    as HFT5Normalizer does — proving the gate is mirrored in the parent."""
    monkeypatch.setattr(
        t5_subprocess.subprocess, "run",
        _fake_run(stdout=_OUT_MARKER + "a voltage regulator."),
    )
    norm = SubprocessT5Normalizer("some/model", on_faithfulness_failure="repair")
    out = norm.normalize("AMS1117 3.3V regulator")
    assert out.startswith("a voltage regulator")
    assert "must include:" in out
    assert "ams1117" in out


def test_faithfulness_raise_mode(monkeypatch):
    monkeypatch.setattr(
        t5_subprocess.subprocess, "run",
        _fake_run(stdout=_OUT_MARKER + "a regulator"),
    )
    norm = SubprocessT5Normalizer("some/model", on_faithfulness_failure="raise")
    with pytest.raises(ValueError):
        norm.normalize("AMS1117 regulator")


def test_empty_output_raises(monkeypatch):
    # The worker .strip()s before emitting, so an all-whitespace decode reaches
    # the parent as marker + "" -> the empty-check (matching HFT5Normalizer) fires.
    monkeypatch.setattr(
        t5_subprocess.subprocess, "run",
        _fake_run(stdout=_OUT_MARKER),
    )
    norm = SubprocessT5Normalizer("some/model")
    with pytest.raises(ValueError):
        norm.normalize("anything")


def test_nonzero_exit_raises_for_pipeline_fallback(monkeypatch):
    monkeypatch.setattr(
        t5_subprocess.subprocess, "run",
        _fake_run(returncode=1, stderr="[t5-worker] RuntimeError: no torch"),
    )
    norm = SubprocessT5Normalizer("some/model")
    with pytest.raises(RuntimeError, match="T5 subprocess failed"):
        norm.normalize("anything")


def test_timeout_raises(monkeypatch):
    monkeypatch.setattr(
        t5_subprocess.subprocess, "run",
        _fake_run(raises=subprocess.TimeoutExpired(cmd="x", timeout=1)),
    )
    norm = SubprocessT5Normalizer("some/model", timeout_s=1)
    with pytest.raises(RuntimeError, match="timed out"):
        norm.normalize("anything")


def test_missing_marker_raises(monkeypatch):
    """Stray stdout without the marker must not be mistaken for model output."""
    monkeypatch.setattr(
        t5_subprocess.subprocess, "run",
        _fake_run(stdout="some unrelated log line\n"),
    )
    norm = SubprocessT5Normalizer("some/model")
    with pytest.raises(RuntimeError, match="no output marker"):
        norm.normalize("anything")


def test_launch_failure_raises(monkeypatch):
    monkeypatch.setattr(
        t5_subprocess.subprocess, "run",
        _fake_run(raises=OSError("No such file")),
    )
    norm = SubprocessT5Normalizer("some/model")
    with pytest.raises(RuntimeError, match="could not launch"):
        norm.normalize("anything")


def test_pipeline_falls_back_to_raw_prompt_on_worker_failure(monkeypatch):
    """End-to-end: a failing normalizer must NOT crash run(); the raw prompt flows
    on to Qwen (mirrors pipeline.run's existing except-clause)."""
    from inference.pipeline import OhmaticPipeline

    pipe = OhmaticPipeline.mock()

    class _Boom:
        def normalize(self, prompt):
            raise RuntimeError("worker exploded")

    pipe.normalizer = _Boom()
    result = pipe.run("a 5v regulator")
    # mock Qwen returns an ERC-passing stub, so the run still completes ok.
    assert result.ok
