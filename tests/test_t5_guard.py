"""Request-preservation guard: T5 must ENRICH the request, never REPLACE it.

On out-of-distribution prompts the T5 normalizer can silently swap the request for
a memorized circuit. The guard detects subject drift and the normalizer falls back
to the raw prompt, so a bad rewrite can never corrupt what Qwen builds.

Pure-Python / torch-free: the subject-drift primitive is tested directly, and the
end-to-end fallback is tested via SubprocessT5Normalizer with the worker stubbed.
"""
import subprocess

from shared.t5_normalizer import subject_recall, REQUEST_RECALL_MIN
from inference import t5_subprocess
from inference.t5_subprocess import SubprocessT5Normalizer, _OUT_MARKER


# (raw request, T5 output that REPLACED it with an unrelated circuit) — real cases
SUBSTITUTIONS = [
    ("hook up an ldr so my arduino knows when its dark needs to read on an analog pin 5v",
     "Design an LM317 adjustable linear regulator module. U1 (LM317, TO-220) takes "
     "unregulated 15 V on VIN_NET and outputs regulated voltage on VCC."),
    ("make a lil power supply that turns 24v into 12v for a fan idk how many amps maybe half an amp",
     "Design a 12V temperature-controlled fan circuit. NTC1 (10 k NTC thermistor) and "
     "R1 (10 k) form a divider from VCC to GND; as temperature rises NTC resistance falls."),
]

# (raw request, faithful enrichment of the SAME circuit) — must pass through
FAITHFUL = [
    ("make an output that can push current both ways",
     "Design a push-pull (totem-pole) output stage for a 5V supply. Q1 (PNP, emitter to "
     "VCC) sources current during positive swings while Q2 (NPN) sinks current."),
    ("comparator threshold flag with led",
     "Make a comparator board where S1 is compared against a resistor-divider threshold, "
     "the output is pulled up, and an LED shows the limit state."),
    ("Design a 5V to 3.3V linear regulator that can deliver at least 500mA with proper "
     "input and output decoupling capacitors.",
     "Design a 3.3 V LDO power module using the AP2112K-3.3 (SOT-25). Input is 5 V (raw). "
     "C1 and C2 decouple the input; C3 and C4 stabilise the 3.3 V output."),
]


def test_subject_guard_flags_substitutions():
    for raw, out in SUBSTITUTIONS:
        r = subject_recall(raw, out)
        assert r < REQUEST_RECALL_MIN, f"missed substitution ({r:.0%}): {raw!r} -> {out!r}"


def test_subject_guard_keeps_faithful_enrichments():
    for raw, out in FAITHFUL:
        r = subject_recall(raw, out)
        assert r >= REQUEST_RECALL_MIN, f"false positive ({r:.0%}): {raw!r} -> {out!r}"


def _stub_worker(monkeypatch, output: str):
    def _run(cmd, input=None, capture_output=None, timeout=None):
        return subprocess.CompletedProcess(cmd, 0, (_OUT_MARKER + output).encode("utf-8"), b"")
    monkeypatch.setattr(t5_subprocess.subprocess, "run", _run)


def test_normalize_falls_back_to_raw_on_subject_drift(monkeypatch):
    raw, swapped = SUBSTITUTIONS[0]
    _stub_worker(monkeypatch, swapped)
    norm = SubprocessT5Normalizer("some/model")          # default mode = fallback
    assert norm.normalize(raw) == raw                    # used the raw prompt, not the swap


def test_default_fallback_on_swapped_supply_voltage(monkeypatch):
    """ru-009-style: subject survives but the supply was swapped (12V -> 5V). The
    entity gate's default 'fallback' returns the raw prompt rather than ship the
    wrong circuit."""
    raw = ("Design a constant-current driver for a single 1W white LED running from "
           "12V, targeting about 350mA.")
    swapped = ("Design a single-channel NPN transistor LED driver. Q1 (2N3904) switches "
               "an LED (LED1, red 3 mm) from a 5 V supply.")
    _stub_worker(monkeypatch, swapped)
    norm = SubprocessT5Normalizer("some/model")
    assert norm.normalize(raw) == raw


def test_faithful_normalization_passes_through(monkeypatch):
    raw, good = FAITHFUL[2]
    _stub_worker(monkeypatch, good)
    norm = SubprocessT5Normalizer("some/model")
    assert norm.normalize(raw) == good
