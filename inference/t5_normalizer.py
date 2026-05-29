#!/usr/bin/env python3
"""T5-style prompt normalizer for the Step 2 parser pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass

try:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
except ModuleNotFoundError:
    AutoModelForSeq2SeqLM = None
    AutoTokenizer = None


T5_MODEL_ID = "google/flan-t5-base"
T5_TASK_PREFIX = "normalize ohmatic request: "
NORMALIZED_INTENT_PREFIX = "ohmatic_intent_v1 | "


def clean_prompt(prompt: str) -> str:
    return " ".join(prompt.split())


def build_t5_input(prompt: str, prefix: str = T5_TASK_PREFIX) -> str:
    cleaned = clean_prompt(prompt)
    if not cleaned:
        raise ValueError("prompt must not be empty")
    return f"{prefix}{cleaned}"


@dataclass(frozen=True)
class T5NormalizerConfig:
    model_id: str = T5_MODEL_ID
    max_new_tokens: int = 256
    num_beams: int = 1


class StaticT5Normalizer:
    """Offline adapter used for tests and mock runs when no T5 checkpoint is loaded."""

    def normalize(self, prompt: str) -> str:
        raw_request = clean_prompt(prompt)
        if not raw_request:
            raise ValueError("prompt must not be empty")
        return (
            f"{NORMALIZED_INTENT_PREFIX}"
            f"raw_request={raw_request} | "
            "requirements=use_registry_component_types,connect_every_declared_pin,"
            "include_power_vcc_and_power_gnd,assist_qwen_parser_without_authoring_json,"
            "forbid_bom_supplier_price_stock_url_api_keys"
        )


class T5Normalizer:
    """Hugging Face seq2seq normalizer for raw NL request -> normalized intent text."""

    def __init__(self, config: T5NormalizerConfig | None = None) -> None:
        if AutoTokenizer is None or AutoModelForSeq2SeqLM is None:
            raise RuntimeError(
                "transformers is required for T5 normalization. Install requirements.txt "
                "or use StaticT5Normalizer for offline tests."
            )
        self.config = config or T5NormalizerConfig()
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_id)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.config.model_id)

    def normalize(self, prompt: str) -> str:
        source_text = build_t5_input(prompt)
        encoded = self.tokenizer(source_text, return_tensors="pt")
        encoded = self._to_model_device(encoded)
        generated = self.model.generate(
            **encoded,
            max_new_tokens=self.config.max_new_tokens,
            num_beams=self.config.num_beams,
            do_sample=False,
        )
        normalized = self.tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        if not normalized:
            raise ValueError("T5 produced empty normalization")
        validate_helper_text(normalized)
        return normalized

    def _to_model_device(self, encoded):
        device = getattr(self.model, "device", None)
        if device is None:
            return encoded
        if hasattr(encoded, "to"):
            return encoded.to(device)
        return {
            key: value.to(device) if hasattr(value, "to") else value
            for key, value in encoded.items()
        }


def validate_helper_text(text: str) -> None:
    """Reject T5 helper outputs that try to become final circuit JSON."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("T5 produced empty normalization")
    lowered = stripped.lower()
    if '"components"' in lowered or '"nets"' in lowered:
        raise ValueError("T5 helper must not emit final circuit JSON")
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return
    if isinstance(parsed, dict) and ({"components", "nets"} & set(parsed)):
        raise ValueError("T5 helper must not emit final circuit JSON")
