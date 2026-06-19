"""inference.qwen_chat.render_chat: pure-Python Qwen3 ChatML.

Two layers:
  1. CI-always unit tests that pin the exact rendered string for the shapes the
     pipeline emits (no transformers needed) - these lock the format.
  2. An opt-in parity test that asserts byte-identity with the REAL
     transformers.apply_chat_template, skipped unless transformers + a Qwen
     tokenizer dir are available (set OHMATIC_QWEN_TOKENIZER_DIR, or have
     models/Ohmatic-Qwen3-8B-tokenizer present). This is the proof that dropping
     transformers introduces zero prompt drift.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inference.qwen_chat import render_chat

_GEN = "<|im_start|>assistant\n<think>\n\n</think>\n\n"  # add_generation_prompt + enable_thinking=False tail


def test_module_import_is_dependency_free():
    """Importing the renderer must NOT pull transformers or torch. Checked in a
    fresh subprocess so it is independent of what other tests imported."""
    code = ("import sys, inference.qwen_chat\n"
            "assert 'transformers' not in sys.modules, 'transformers leaked'\n"
            "assert 'torch' not in sys.modules, 'torch leaked'\n")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          cwd=str(Path(__file__).resolve().parents[1]))
    assert proc.returncode == 0, proc.stderr


def test_single_turn():
    msgs = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]
    assert render_chat(msgs) == (
        "<|im_start|>system\nSYS<|im_end|>\n"
        "<|im_start|>user\nhi<|im_end|>\n" + _GEN)


def test_one_retry_turn():
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"}, {"role": "user", "content": "u2"}]
    assert render_chat(msgs) == (
        "<|im_start|>system\nS<|im_end|>\n"
        "<|im_start|>user\nu1<|im_end|>\n"
        "<|im_start|>assistant\na1<|im_end|>\n"
        "<|im_start|>user\nu2<|im_end|>\n" + _GEN)


def test_think_block_stripped_from_assistant_history():
    # An assistant turn carrying <think>..</think> in HISTORY (not trailing) renders
    # only the post-</think> content - mirrors the template's split logic.
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"},
            {"role": "assistant", "content": "reasoning</think>ANSWER"},
            {"role": "user", "content": "u2"}]
    assert render_chat(msgs) == (
        "<|im_start|>system\nS<|im_end|>\n"
        "<|im_start|>user\nu<|im_end|>\n"
        "<|im_start|>assistant\nANSWER<|im_end|>\n"
        "<|im_start|>user\nu2<|im_end|>\n" + _GEN)


def test_no_generation_prompt():
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"}]
    assert render_chat(msgs, add_generation_prompt=False) == (
        "<|im_start|>system\nS<|im_end|>\n<|im_start|>user\nu<|im_end|>\n")


# ── opt-in byte-identity proof vs the real transformers tokenizer ─────────────

def _tokenizer_dir():
    env = os.environ.get("OHMATIC_QWEN_TOKENIZER_DIR")
    if env and Path(env).is_dir():
        return env
    default = Path(__file__).resolve().parents[1] / "models" / "Ohmatic-Qwen3-8B-tokenizer"
    return str(default) if (default / "tokenizer_config.json").exists() else None


_TOK_DIR = _tokenizer_dir()
_HAS_TF = importlib.util.find_spec("transformers") is not None


@pytest.mark.skipif(_TOK_DIR is None or not _HAS_TF,
                    reason="real Qwen tokenizer + transformers required "
                           "(set OHMATIC_QWEN_TOKENIZER_DIR or run ./ohmatic fetch)")
@pytest.mark.parametrize("msgs", [
    [{"role": "system", "content": "SYS PROMPT"}, {"role": "user", "content": "5V to 3.3V LDO"}],
    [{"role": "system", "content": "S"}, {"role": "user", "content": "led"},
     {"role": "assistant", "content": '{"x": 1}'}, {"role": "user", "content": "ERC: MISSING_POWER_VCC"}],
    [{"role": "system", "content": "S"}, {"role": "user", "content": "a"},
     {"role": "assistant", "content": '{"a":1}'}, {"role": "user", "content": "f1"},
     {"role": "assistant", "content": '{"b":2}'}, {"role": "user", "content": "f2"}],
    [{"role": "system", "content": "S"}, {"role": "user", "content": "unicode café ± Ω\nmulti\nline"}],
    [{"role": "system", "content": "S"}, {"role": "user", "content": ""}],
    [{"role": "system", "content": "S"}, {"role": "user", "content": "q"},
     {"role": "assistant", "content": '{"v": "x</think>y"}'}, {"role": "user", "content": "fb"}],
])
def test_render_chat_byte_identical_to_transformers(msgs):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(_TOK_DIR)
    golden = tok.apply_chat_template(msgs, tokenize=False,
                                     add_generation_prompt=True, enable_thinking=False)
    assert render_chat(msgs) == golden
