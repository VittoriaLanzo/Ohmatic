"""Cross-language parity for the doctor's OS-reserve math.

The dynamic OS reserve and the Q4 committed-peak decision are implemented THREE
times - Python (gateway/stub/server.py), bash (ohmatic), PowerShell (ohmatic.ps1).
If they drift, the doctor could recommend a tier the gateway guard then refuses.
These tests drive each launcher's hidden `__hwprobe "<total_mb>:<avail_mb>"` seam
and assert it agrees with the Python reference (and hence the guard).

bash runs anywhere bash exists (incl. Linux CI); the PowerShell leg is win32-only.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_OHMATIC = _ROOT / "ohmatic"
_OHMATIC_PS1 = _ROOT / "ohmatic.ps1"

# Must stay equal to server.py _KV/_RAM constants and both launchers.
_Q4_COMMITTED_MB = 9146
_FLOOR, _CAP, _FALLBACK = 768, 3072, 2048

# (total_mb, avail_mb|None): floor, in-band, cap, fallback, and the lean-box win.
_CASES = [
    (6000, 5500),    # used 500  -> floor 768
    (16000, 13000),  # used 3000 -> 3000 (in band)
    (16000, 9000),   # used 7000 -> cap 3072
    (6000, None),    # avail unknown -> fallback 2048
    (10240, 9800),   # lean ~10 GB box -> floor 768, q4 fits (the win)
]


def _py_reserve(total, avail):
    if avail is None:
        return _FALLBACK
    return max(_FLOOR, min(max(0, total - avail), _CAP))


def _expected(total, avail):
    r = _py_reserve(total, avail)
    return r, ("yes" if total >= _Q4_COMMITTED_MB + r else "no")


def _parse(out):
    line = next(l for l in out.splitlines() if l.startswith("reserve="))
    d = dict(tok.split("=") for tok in line.split())
    return int(d["reserve"]), d["q4_cpu"]


def _token(total, avail):
    return f"{total}:" if avail is None else f"{total}:{avail}"


@pytest.mark.skipif(not shutil.which("bash"), reason="bash not available")
@pytest.mark.parametrize("total,avail", _CASES)
def test_bash_doctor_reserve_matches_python(total, avail):
    proc = subprocess.run(
        # Relative name + cwd: Git/MSYS bash on Windows mangles an absolute C:\ /
        # C:/ path, but resolves "./ohmatic" against the process cwd fine.
        ["bash", "./ohmatic", "__hwprobe", _token(total, avail)],
        capture_output=True, text=True, cwd=str(_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert _parse(proc.stdout) == _expected(total, avail)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell launcher is win32-only")
@pytest.mark.parametrize("total,avail", _CASES)
def test_powershell_doctor_reserve_matches_python(total, avail):
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", _OHMATIC_PS1.as_posix(), "__hwprobe", _token(total, avail)],
        capture_output=True, text=True, cwd=str(_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert _parse(proc.stdout) == _expected(total, avail)
