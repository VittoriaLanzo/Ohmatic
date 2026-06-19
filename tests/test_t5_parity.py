"""Real-model regression: SubprocessT5Normalizer must be byte-identical to the
in-process HFT5Normalizer it replaces on the edge tier.

This is the core correctness guarantee of the subprocess isolation: moving T5 out
of the long-lived process buys the RAM back ONLY if the normalization it produces
is unchanged. We assert that against the real model, including the faithfulness
repair path (a dropped specific must be re-attached identically on both sides).

Opt-in: skipped unless a real T5 normalizer and torch are present, so CI stays
green. Point at an installed model with OHMATIC_T5_MODEL_DIR, or run
`./ohmatic fetch` so models/t5-normalizer exists. This file imports torch (for the
in-process leg), so it is kept separate from test_t5_subprocess.py, which must
stay torch-free.
"""
import importlib.util
import os
from pathlib import Path

import pytest

from inference.t5_subprocess import SubprocessT5Normalizer


def _t5_model_dir():
    env = os.environ.get("OHMATIC_T5_MODEL_DIR")
    if env and Path(env).is_dir():
        return env
    default = Path(__file__).resolve().parents[1] / "models" / "t5-normalizer"
    return str(default) if (default / "config.json").exists() else None


_T5_DIR = _t5_model_dir()
_HAS_TORCH = importlib.util.find_spec("torch") is not None

pytestmark = pytest.mark.skipif(
    _T5_DIR is None or not _HAS_TORCH,
    reason="real T5 model + torch required (set OHMATIC_T5_MODEL_DIR or run ./ohmatic fetch)",
)


@pytest.fixture(scope="module")
def normalizers():
    # Build each once: HFT5Normalizer loads the model here; SubprocessT5Normalizer
    # is cheap to construct (it spawns a fresh worker per normalize call).
    from inference.pipeline import HFT5Normalizer
    return (HFT5Normalizer(_T5_DIR, max_new_tokens=256),
            SubprocessT5Normalizer(_T5_DIR, max_new_tokens=256))


@pytest.mark.parametrize("prompt", [
    "blinky light",                                      # clueless: faithfulness no-op
    "5V to 3.3V LDO with reverse-polarity protection",  # carries user specifics
    "i need a 555 timr astable at 1hz, 9v",             # typos + a dropped specific -> repair gate
])
def test_subprocess_t5_is_byte_identical_to_in_process(normalizers, prompt):
    hf, sub = normalizers
    assert sub.normalize(prompt) == hf.normalize(prompt)
