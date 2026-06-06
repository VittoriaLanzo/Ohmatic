"""
inference/pipeline.py
=====================
Full Ohmatic inference pipeline:

    User (any style)
        ↓
    T5 normalizer          — maps diverse NL to clean technical description
        ↓
    Qwen generator         — generates circuit JSON from normalized prompt
        ↓
    ERC static checker     — validates the circuit against all rules
        ↓
    [errors?] → Qwen retry — appends ERC error message; Qwen corrects the JSON
        ↓
    Return circuit or final error report

Key invariant: Qwen always receives normalized text (T5 output format), matching
its training distribution. Raw user prompts NEVER reach Qwen directly.

Usage:
    from inference.pipeline import OhmaticPipeline, PipelineConfig

    cfg = PipelineConfig(t5_model_id="path/to/t5", qwen_model_id="path/to/qwen")
    pipeline = OhmaticPipeline(cfg)
    result = pipeline.run("solar panel boost converter circuit")
    if result.ok:
        print(result.circuit_json)
    else:
        print(result.errors)

Mock/test mode:
    pipeline = OhmaticPipeline.mock()
    result = pipeline.run("LED blinker")
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

# ── ERC checker ───────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    # Use analyze_schematic — the SAME validity standard as training/the held-out benchmark
    # (structural/schema validation via _validator + forbidden-field checks + the electrical
    # rules). The old path here ran ONLY electrical_diagnostics, skipping structural validation,
    # so prod passed malformed circuits the benchmark would fail (pass@1 inflated ~0.9 vs the
    # real ~0.50). Single-sourcing on analyze_schematic makes eval == prod == benchmark.
    from eval.diagnostics import analyze_schematic as _analyze_schematic

    def _run_erc(circuit: dict) -> list[dict]:
        return _analyze_schematic(circuit).get("diagnostics", [])

    ERC_AVAILABLE = True
except Exception as _exc:
    ERC_AVAILABLE = False

    def _run_erc(circuit: dict) -> list[dict]:
        return []  # ERC unavailable — pass through


# ── Protocol interfaces (model-agnostic) ──────────────────────────────────────

class TextNormalizer(Protocol):
    """T5 stage: raw NL → normalized NL."""
    def normalize(self, prompt: str) -> str: ...


class ChatModel(Protocol):
    """Qwen stage: list[{role, content}] → assistant response str."""
    def chat(self, messages: list[dict[str, str]]) -> str: ...


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class PipelineConfig:
    # T5 normalizer — trained Ohmatic restyler (held-out test: exact_match 52% vs 0.3% baseline,
    # entity_preservation 81%). Falls back conceptually to "google/flan-t5-base" if unavailable.
    t5_model_id: str = "VittoriaLanzo/ohmatic-t5-normalizer"
    t5_max_new_tokens: int = 256

    # Qwen generator
    qwen_model_id: str = "Qwen/Qwen3-8B"   # base model
    qwen_adapter_id: str = ""              # trained LoRA adapter (HF repo or local dir)
    qwen_adapter_revision: str = ""        # e.g. "best-erc" / "latest"
    qwen_max_new_tokens: int = 2560        # matches training/eval; longest valid circuit ~2.2k
    qwen_attn_implementation: str = "flash_attention_2"  # FA2 if available, else graceful fallback

    # ERC retry loop — greedy decoding (set in HFChatModel) for deterministic JSON
    max_retries: int = 3                   # max ERC correction attempts (the "N shots")

    # System prompt paths
    schema_path: Path = _ROOT / "schema.md"
    registry_path: Path = _ROOT / "verifier" / "config" / "component_registry.toml"
    erc_rules_path: Path = _ROOT / "dataset" / "generated" / "erc_rules_reference.jsonl"


# ── Results ───────────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    ok: bool
    circuit: dict | None = None
    circuit_json: str = ""
    normalized_prompt: str = ""
    attempts: int = 0
    erc_errors: list[dict] = field(default_factory=list)
    parse_error: str = ""

    def __str__(self) -> str:
        if self.ok:
            return f"PipelineResult(ok=True, attempts={self.attempts})"
        return (
            f"PipelineResult(ok=False, attempts={self.attempts}, "
            f"erc_errors={len(self.erc_errors)}, parse_error={self.parse_error!r})"
        )


# ── System prompt builder ─────────────────────────────────────────────────────

# System prompt + ERC feedback come from the SHARED single sources of truth — the exact
# same functions the training data was built with — so what the model is SERVED is
# byte-identical to what it was TRAINED on. The previous inline versions here had drifted
# (stale flat schema; a different ERC-error layout) and would have served the model
# out-of-distribution prompts + feedback.
from shared.prompt_builder import build_system_prompt as _shared_system_prompt
from shared.erc_feedback import format_erc_errors as _format_erc_errors
from shared.t5_normalizer import (
    T5_TASK_PREFIX as _T5_PREFIX,
    add_prefix as _t5_add_prefix,
    faithfulness as _t5_faithfulness,
    looks_non_english as _t5_non_english,
)


def _build_system_prompt(
    schema_text: str = "",
    registry: dict | None = None,
    erc_rules: list[dict] | None = None,
) -> str:
    """Standardized Ohmatic system prompt (schema + full registry + full ERC catalog),
    from shared/prompt_builder. Args are ignored (kept for call-site compatibility) —
    the canonical config drives everything."""
    return _shared_system_prompt()


def _parse_circuit(text: str) -> tuple[dict | None, str]:
    """
    Parse circuit JSON from model output.
    Returns (circuit_dict, error_msg). error_msg is empty on success.
    """
    text = text.strip()

    # Direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, ""
    except json.JSONDecodeError:
        pass

    # Try to extract JSON block (in case model leaked prose before/after)
    import re
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            obj = json.loads(match.group())
            if isinstance(obj, dict):
                return obj, ""
        except json.JSONDecodeError:
            pass

    return None, f"Model output is not valid JSON: {text[:200]!r}"


# ── Default resource loader ───────────────────────────────────────────────────

def _load_system_resources(cfg: PipelineConfig) -> tuple[str, dict | None, list[dict] | None]:
    """Load schema, registry, and ERC rules. Returns (schema_text, registry, rules)."""
    schema_text = ""
    if cfg.schema_path.exists():
        schema_text = cfg.schema_path.read_text(encoding="utf-8")

    registry = None
    if cfg.registry_path.exists():
        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            registry = tomllib.loads(cfg.registry_path.read_text(encoding="utf-8"))
            registry.pop("defaults", None)
        except Exception:
            registry = None

    erc_rules = None
    if cfg.erc_rules_path.exists():
        try:
            erc_rules = [
                json.loads(line)
                for line in cfg.erc_rules_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception:
            erc_rules = None

    return schema_text, registry, erc_rules


# ── Mock adapters (for testing without loaded models) ─────────────────────────

class _MockNormalizer:
    """Passes the prompt through unchanged (no T5 loaded)."""
    def normalize(self, prompt: str) -> str:
        return prompt.strip()


class _MockQwen:
    """Returns a trivial ERC-passing circuit stub for testing."""
    _STUB = {
        "metadata": {
            "title": "Mock Circuit",
            "description": "Auto-generated mock for testing.",
            "version": "0.1",
            "tags": ["mock"],
        },
        "STAGE_1_TOPOLOGY": {
            "components": [
                {"id": "VCC1", "type": "power_vcc", "value": "5V", "part": "VCC",
                 "pins": {"1": "VCC"}},
                {"id": "GND1", "type": "power_gnd", "value": "0V", "part": "GND",
                 "pins": {"1": "GND"}},
                {"id": "R1", "type": "resistor", "value": "1k", "part": "0603",
                 "pins": {"1": "VCC", "2": "GND"}},
            ],
            "nets": [
                {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
                {"name": "GND", "pins": ["GND1.1", "R1.2"]},
            ],
        },
        "STAGE_2_LAYOUT": {
            "spatial_nodes": [
                {"id": "VCC1", "x": 0, "y": 0},
                {"id": "GND1", "x": 0, "y": 10},
                {"id": "R1",   "x": 5, "y": 5},
            ],
        },
    }

    def chat(self, messages: list[dict[str, str]]) -> str:
        return json.dumps(self._STUB, ensure_ascii=False)


# ── HuggingFace adapters ──────────────────────────────────────────────────────

class HFChatModel:
    """Wrap a HuggingFace AutoModelForCausalLM for chat-format inference."""

    def __init__(
        self,
        model_id: str,
        adapter_id: str | None = None,
        adapter_revision: str | None = None,
        max_new_tokens: int = 2560,
        device_map: str = "auto",
        attn_implementation: str = "flash_attention_2",
    ) -> None:
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            raise RuntimeError("Install transformers: pip install transformers")
        import torch as _torch

        # Tokenizer: prefer the adapter's (it carries the trained chat template). But a LoRA
        # adapter repo often lacks a fast `tokenizer.json`, forcing a slow->fast CONVERSION that
        # can fail on the pod ("need sentencepiece or tiktoken..."). A LoRA never changes the
        # tokenizer, so on any failure we fall back to the BASE model, which ships a complete
        # fast tokenizer and loads cleanly with no conversion.
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(adapter_id or model_id)
        except Exception as _tok_exc:
            print(f"[HFChatModel] adapter tokenizer load failed ({_tok_exc}); "
                  f"falling back to base {model_id}.", file=sys.stderr, flush=True)
            self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        # Prefer FlashAttention-2 (Ampere/A40 supported) — ~2x faster generation than the
        # sdpa/xformers fallback on the long 6.2k-token prompts. GRACEFUL: FA2 is a SPEEDUP, not
        # a correctness requirement, so if flash-attn is not installed/loadable we fall back to
        # the default attention instead of crashing. The active impl is logged so a smoke run
        # tells us whether FA2 actually engaged.
        _load = dict(device_map=device_map, torch_dtype=_torch.bfloat16, low_cpu_mem_usage=True)
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id, attn_implementation=attn_implementation, **_load)
        except Exception as _fa_exc:
            print(f"[HFChatModel] attn '{attn_implementation}' unavailable ({_fa_exc}); "
                  f"falling back to default attention.", file=sys.stderr, flush=True)
            self.model = AutoModelForCausalLM.from_pretrained(model_id, **_load)
        if adapter_id:
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(
                self.model, adapter_id, revision=adapter_revision)
        self.model.eval()
        self.max_new_tokens = max_new_tokens
        _impl = getattr(self.model.config, "_attn_implementation", "?")
        print(f"[HFChatModel] loaded {model_id} (+adapter={adapter_id or 'none'}"
              f"@{adapter_revision or '-'})  attn={_impl}", file=sys.stderr, flush=True)

    def chat(self, messages: list[dict[str, str]]) -> str:
        # GREEDY decoding (do_sample=False) + enable_thinking=False — identical to how the
        # model was trained and evaluated. Sampling here would make serving drift from
        # training and add nondeterminism to a structured-JSON task.
        try:
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
        with __import__("torch").no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,            # greedy — temperature intentionally absent
                pad_token_id=self.tokenizer.eos_token_id,
            )
        n_input = inputs["input_ids"].shape[1]
        return self.tokenizer.decode(output[0][n_input:], skip_special_tokens=True).strip()


class HFT5Normalizer:
    """Wrap a HuggingFace Seq2SeqLM checkpoint as the T5 normalizer.

    SCOPE: English only (see shared.t5_normalizer.looks_non_english). Non-English input is
    out of scope and is logged as a warning.

    HARD FAITHFULNESS GATE: T5's only legitimate failure is dropping a specific the user gave
    (e.g. "3.3V isolated RS-485" -> generic "RS-485"). After generating, we compare entities
    (voltages / part numbers / values) in the user input vs the normalized output:
      - on_faithfulness_failure="repair" (default): re-attach the dropped specifics so Qwen
        still receives them (constructive, never fails the request).
      - "raise": fail fast and loud.
      - "warn": log only.
    Clueless inputs carry no specifics, so the gate is a no-op for them by construction.
    """

    TASK_PREFIX = _T5_PREFIX  # single-sourced (shared.t5_normalizer)

    def __init__(
        self,
        model_id: str,
        max_new_tokens: int = 256,
        device_map: str = "auto",
        on_faithfulness_failure: str = "repair",
        check_english: bool = True,
    ) -> None:
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError:
            raise RuntimeError("Install transformers: pip install transformers")

        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            model_id, device_map=device_map
        )
        self.max_new_tokens = max_new_tokens
        self.on_faithfulness_failure = on_faithfulness_failure
        self.check_english = check_english

    def normalize(self, prompt: str) -> str:
        if self.check_english and _t5_non_english(prompt):
            print(f"[t5] WARNING: input looks non-English; Ohmatic supports English only. "
                  f"Proceeding best-effort.", file=sys.stderr)

        src = _t5_add_prefix(prompt)
        inputs = self.tokenizer(src, return_tensors="pt").to(self.model.device)
        with __import__("torch").no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                num_beams=4,
                do_sample=False,
            )
        normalized = self.tokenizer.decode(output[0], skip_special_tokens=True).strip()
        if not normalized:
            raise ValueError("T5 produced empty normalization")

        # ── Hard faithfulness gate ──────────────────────────────────────────────────
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


# ── Main pipeline ─────────────────────────────────────────────────────────────

class OhmaticPipeline:
    """
    T5 → Qwen → ERC → [retry] pipeline.

    Args:
        normalizer: TextNormalizer instance (T5 adapter)
        generator: ChatModel instance (Qwen adapter)
        system_prompt: Pre-built system prompt string
        max_retries: Max ERC correction attempts before giving up
    """

    def __init__(
        self,
        normalizer: TextNormalizer,
        generator: ChatModel,
        system_prompt: str,
        max_retries: int = 3,
    ) -> None:
        self.normalizer = normalizer
        self.generator = generator
        self.system_prompt = system_prompt
        self.max_retries = max_retries

    @classmethod
    def from_config(cls, cfg: PipelineConfig) -> "OhmaticPipeline":
        """Build pipeline from PipelineConfig, loading HF models."""
        # System prompt = the shared single source (exactly what the model trained on).
        system_prompt = _build_system_prompt()

        normalizer: TextNormalizer
        if cfg.t5_model_id:
            normalizer = HFT5Normalizer(cfg.t5_model_id, max_new_tokens=cfg.t5_max_new_tokens)
        else:
            normalizer = _MockNormalizer()

        generator: ChatModel
        if cfg.qwen_model_id or cfg.qwen_adapter_id:
            generator = HFChatModel(
                cfg.qwen_model_id or "Qwen/Qwen3-8B",
                adapter_id=cfg.qwen_adapter_id or None,
                adapter_revision=cfg.qwen_adapter_revision or None,
                max_new_tokens=cfg.qwen_max_new_tokens,
                attn_implementation=cfg.qwen_attn_implementation,
            )
        else:
            generator = _MockQwen()

        return cls(normalizer, generator, system_prompt, max_retries=cfg.max_retries)

    @classmethod
    def mock(cls, schema_path: Path | None = None) -> "OhmaticPipeline":
        """Construct a fully mocked pipeline for testing (no models loaded)."""
        return cls(_MockNormalizer(), _MockQwen(), _build_system_prompt(), max_retries=2)

    # ── Core run method ────────────────────────────────────────────────────────

    def run(self, raw_prompt: str) -> PipelineResult:
        """
        Run the full pipeline.

        1. T5 normalizes the raw user prompt.
        2. Qwen generates a circuit JSON.
        3. ERC validates the circuit.
        4. On failure: append ERC errors, let Qwen retry.
        5. Return result after max_retries or first passing circuit.
        """
        if not raw_prompt.strip():
            return PipelineResult(ok=False, parse_error="Empty prompt")

        # ── Step 1: T5 normalization ───────────────────────────────────────────
        try:
            normalized = self.normalizer.normalize(raw_prompt)
        except Exception as exc:
            # Normalizer failure → fall through with raw prompt
            normalized = raw_prompt.strip()
            print(f"[pipeline] T5 normalizer error ({exc}), using raw prompt", flush=True)

        # ── Step 2+: Qwen generation with ERC loopback ────────────────────────
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": normalized},
        ]

        last_circuit: dict | None = None
        last_erc_errors: list[dict] = []
        last_parse_error = ""

        for attempt in range(1, self.max_retries + 2):  # +1 for the initial attempt
            # Generate
            try:
                response = self.generator.chat(messages)
            except Exception as exc:
                return PipelineResult(
                    ok=False,
                    normalized_prompt=normalized,
                    attempts=attempt,
                    parse_error=f"Generator error: {exc}",
                )

            # Parse JSON
            circuit, parse_error = _parse_circuit(response)
            last_parse_error = parse_error

            if circuit is None:
                if attempt > self.max_retries:
                    break
                # Ask Qwen to fix its JSON syntax
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": (
                        "The output above is not valid JSON. "
                        "Return ONLY a valid JSON object — no prose, no markdown fences."
                    ),
                })
                continue

            last_circuit = circuit

            # ERC check. _run_erc now returns analyze_schematic's full diagnostics, whose
            # validity standard is `valid = not diagnostics` — i.e. ANY diagnostic is blocking.
            # So treat every returned diagnostic as a failure (matching training/benchmark
            # exactly). Filtering by severity here would pass circuits the benchmark fails.
            erc_diags = _run_erc(circuit)
            failures = list(erc_diags)
            last_erc_errors = failures

            if not failures:
                # ✓ Circuit passes ERC — done
                return PipelineResult(
                    ok=True,
                    circuit=circuit,
                    circuit_json=json.dumps(circuit, ensure_ascii=False),
                    normalized_prompt=normalized,
                    attempts=attempt,
                )

            if attempt > self.max_retries:
                break  # Exhausted retries

            # Append bad circuit + ERC errors to conversation → Qwen retry
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": _format_erc_errors(failures),
            })

        # Exhausted retries — return best (last) circuit with error info
        return PipelineResult(
            ok=False,
            circuit=last_circuit,
            circuit_json=json.dumps(last_circuit, ensure_ascii=False) if last_circuit else "",
            normalized_prompt=normalized,
            attempts=self.max_retries + 1,
            erc_errors=last_erc_errors,
            parse_error=last_parse_error,
        )
