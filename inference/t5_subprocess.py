"""Run the T5 normalizer in a SHORT-LIVED subprocess so the long-lived inference
process never imports torch.

On the GGUF/CPU edge tier the Qwen generator (llama.cpp) is torch-free, so torch
(~2 GiB resident) + accelerate + flan-t5-base (~1 GiB fp32) exist purely for T5.
T5 runs EXACTLY ONCE at the start of pipeline.run(), then sits idle through all
1-4 Qwen passes. By moving T5 into a subprocess that exits the instant it has
produced its single normalization, the OS reclaims ~3 GiB BEFORE Qwen builds its
KV/prefix cache, so the T5 cost and the Qwen cost never stack (peak ~12 GiB -> ~9 GiB).

Two halves live in this file:

  * The WORKER (`_run_worker`, invoked via `python -m inference.t5_subprocess`):
    imports torch + transformers, loads the SAME model in the SAME dtype with the
    SAME generation params as inference.pipeline.HFT5Normalizer, runs ONE
    generation, prints ONLY the normalized string to stdout, and exits.

  * The PARENT class (`SubprocessT5Normalizer`): spawns the worker via
    sys.executable on each normalize() call, captures stdout, and applies the
    faithfulness gate IN-PROCESS using the PURE-PYTHON helpers in
    shared.t5_normalizer. It NEVER imports torch.

IMPORTANT: nothing at module top level may import torch/transformers — the worker
imports them lazily inside `_run_worker`, so this module stays importable on
torch-free machines (and so the parent process stays torch-free).
"""
from __future__ import annotations

import subprocess
import sys

from shared.t5_normalizer import (
    add_prefix as _t5_add_prefix,
    faithfulness as _t5_faithfulness,
    looks_non_english as _t5_non_english,
)

# Marker the parent looks for to distinguish "the worker ran and produced this
# normalization" from any stray stdout. The worker prints exactly one line:
#   <_OUT_MARKER><normalized text>
# and the parent strips the marker. Using a marker (rather than trusting raw
# stdout) means accidental prints from a transitive import can never be mistaken
# for the model output.
_OUT_MARKER = "\x00OHMATIC_T5_OUT\x00"

# Generous default; a single flan-t5-base beam search on CPU is seconds, but the
# very first call also pays cold model load (download/mmap). The parent treats a
# timeout as a normalizer failure -> pipeline falls back to the raw prompt.
DEFAULT_TIMEOUT_S = 600


# ── Worker (torch is imported ONLY here) ──────────────────────────────────────

def _run_worker(model_id: str, max_new_tokens: int, prompt: str) -> str:
    """Load T5 and produce ONE normalization. Returns the raw decoded string
    (NO faithfulness gate — that runs in the torch-free parent). Mirrors
    HFT5Normalizer.normalize's generation EXACTLY: fp32 (no torch_dtype),
    device_map='auto', num_beams=4, do_sample=False, decode(skip_special_tokens=True).strip().
    """
    # Lazy imports: keep module-level import torch-free.
    # Force offline: the T5 weights are local, so never let transformers/hub phone
    # home (would stall a genuinely offline edge box on first run). Set before import.
    import os as _os
    _os.environ.setdefault("HF_HUB_OFFLINE", "1")
    _os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    # Non-English warning (same wording/stream as HFT5Normalizer; goes to stderr,
    # never stdout, so it cannot pollute the captured output).
    if _t5_non_english(prompt):
        print("[t5] WARNING: input looks non-English; Ohmatic supports English only. "
              "Proceeding best-effort.", file=sys.stderr)

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_id, device_map="auto")

    src = _t5_add_prefix(prompt)
    inputs = tokenizer(src, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            num_beams=4,
            do_sample=False,
        )
    return tokenizer.decode(output[0], skip_special_tokens=True).strip()


def _worker_main(argv: list[str]) -> int:
    """`python -m inference.t5_subprocess <model_id> <max_new_tokens>`; reads the
    prompt from stdin (so prompts with newlines/quotes/length are never an argv
    concern), prints `<_OUT_MARKER><normalized>` to stdout, exits 0. On any error,
    writes a message to stderr and exits nonzero so the parent falls back."""
    try:
        model_id = argv[0]
        max_new_tokens = int(argv[1])
    except (IndexError, ValueError) as exc:
        print(f"[t5-worker] bad args {argv!r}: {exc}", file=sys.stderr)
        return 2

    prompt = sys.stdin.read()
    try:
        normalized = _run_worker(model_id, max_new_tokens, prompt)
    except Exception as exc:  # noqa: BLE001 - any failure -> nonzero exit
        print(f"[t5-worker] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # The empty-check (HFT5Normalizer raises ValueError on empty) is enforced in
    # the parent so the fallback path is uniform; the worker still emits whatever
    # it decoded (possibly empty) behind the marker.
    #
    # Write to the RAW byte buffer (not the text wrapper) so Windows newline
    # translation can never mutate the bytes: the parent captures bytes and
    # decodes UTF-8 itself, so the string after the marker is byte-identical to
    # HFT5Normalizer's tokenizer.decode(...).strip().
    sys.stdout.buffer.write((_OUT_MARKER + normalized).encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0


# ── Parent normalizer (torch-free) ────────────────────────────────────────────

class SubprocessT5Normalizer:
    """TextNormalizer that runs T5 in a short-lived subprocess, then applies the
    faithfulness gate in-process. Drop-in for HFT5Normalizer on the GGUF/edge tier.

    Each normalize() call: spawn worker -> generate once -> worker exits (torch
    reclaimed by OS) -> parent applies the SAME repair/raise/warn gate as
    HFT5Normalizer. This is deliberately NOT a persistent daemon: a daemon would
    keep torch resident and defeat the RAM-reclaim goal.

    On worker failure (nonzero exit, timeout, missing marker), normalize() raises
    so pipeline.run()'s existing except-clause falls back to the raw prompt. The
    parent process is never crashed.
    """

    def __init__(
        self,
        model_id: str,
        max_new_tokens: int = 256,
        on_faithfulness_failure: str = "repair",
        check_english: bool = True,  # accepted for HFT5Normalizer parity; the
        # worker always emits the warning (matching HFT5Normalizer's default).
        timeout_s: int = DEFAULT_TIMEOUT_S,
        python_executable: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.max_new_tokens = max_new_tokens
        self.on_faithfulness_failure = on_faithfulness_failure
        self.check_english = check_english
        self.timeout_s = timeout_s
        self.python_executable = python_executable or sys.executable

    def _spawn(self, prompt: str) -> str:
        """Run the worker once and return its raw (un-gated) decoded output."""
        cmd = [
            self.python_executable,
            "-m", "inference.t5_subprocess",
            self.model_id,
            str(self.max_new_tokens),
        ]
        # Bytes in / bytes out (no text=True): we decode UTF-8 ourselves so the
        # transport is newline-translation-free and the result is byte-identical
        # to HFT5Normalizer's decoded string. stdin gets the raw prompt as UTF-8.
        try:
            proc = subprocess.run(
                cmd,
                input=prompt.encode("utf-8"),
                capture_output=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"T5 subprocess timed out after {self.timeout_s}s"
            ) from exc
        except OSError as exc:  # executable missing, etc.
            raise RuntimeError(f"could not launch T5 subprocess: {exc}") from exc

        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            tail = err[-1] if err else f"exit code {proc.returncode}"
            raise RuntimeError(f"T5 subprocess failed: {tail}")

        out = (proc.stdout or b"").decode("utf-8")
        marker = out.rfind(_OUT_MARKER)
        if marker < 0:
            raise RuntimeError("T5 subprocess produced no output marker")
        return out[marker + len(_OUT_MARKER):]

    def normalize(self, prompt: str) -> str:
        # The decoded string already has skip_special_tokens=True + .strip()
        # applied in the worker (byte-identical to HFT5Normalizer.normalize).
        normalized = self._spawn(prompt)
        if not normalized:
            raise ValueError("T5 produced empty normalization")

        # ── Hard faithfulness gate (identical to HFT5Normalizer) ─────────────
        ratio, missing = _t5_faithfulness(prompt, normalized)
        dropped = sorted(e for kind in missing.values() for e in kind)
        if dropped:
            msg = f"T5 dropped user specifics {dropped} (faithfulness={ratio:.2f})"
            if self.on_faithfulness_failure == "raise":
                raise ValueError(msg)
            print(f"[t5] {msg}", file=sys.stderr)
            if self.on_faithfulness_failure == "repair":
                normalized = f"{normalized.rstrip('.')} (must include: {', '.join(dropped)})."
        return normalized


if __name__ == "__main__":
    raise SystemExit(_worker_main(sys.argv[1:]))
