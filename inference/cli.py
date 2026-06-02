#!/usr/bin/env python3
"""
Command-line interface for circuit generation.

Pipeline: User prompt → T5 normalizer → Qwen generator → ERC checker → [retry]

Usage:
    ohmatic "describe your circuit"
    ohmatic "solar panel boost converter" --t5-model path/to/t5 --qwen-model path/to/qwen
    ohmatic "LED blinker" --mock       # test without loaded models
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from inference.pipeline import OhmaticPipeline, PipelineConfig


def generate_circuit_cli(
    prompt: str,
    t5_model_id: str = "",
    qwen_model_id: str = "",
    temperature: float = 0.2,
    max_retries: int = 3,
    use_mock: bool = False,
) -> Dict[str, Any] | None:
    """
    Run the T5 → Qwen → ERC pipeline and return the circuit dict.

    Args:
        prompt:        Raw user prompt (any NL style)
        t5_model_id:   HF model ID or local path for T5 normalizer
        qwen_model_id: HF model ID or local path for Qwen generator
        temperature:   Qwen sampling temperature (low = more deterministic)
        max_retries:   Max ERC correction attempts
        use_mock:      Use mock models (no loading) — for tests/demos

    Returns:
        Circuit dict or None on failure
    """
    if use_mock:
        pipeline = OhmaticPipeline.mock()
    else:
        cfg = PipelineConfig(
            t5_model_id=t5_model_id,
            qwen_model_id=qwen_model_id,
            qwen_temperature=temperature,
            max_retries=max_retries,
        )
        pipeline = OhmaticPipeline.from_config(cfg)

    print(f"[ohmatic] Prompt: {prompt!r}", file=sys.stderr)
    result = pipeline.run(prompt)

    print(f"[ohmatic] Normalized: {result.normalized_prompt!r}", file=sys.stderr)
    print(f"[ohmatic] Attempts: {result.attempts}  OK: {result.ok}", file=sys.stderr)

    if not result.ok:
        if result.erc_errors:
            print("[ohmatic] Final ERC errors (not fixed after retries):", file=sys.stderr)
            for e in result.erc_errors[:5]:
                print(f"  [{e.get('severity','?')}] {e.get('code','?')}: {e.get('message','')}", file=sys.stderr)
        if result.parse_error:
            print(f"[ohmatic] Parse error: {result.parse_error}", file=sys.stderr)
        # Still return the best attempt if available
        return result.circuit

    return result.circuit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate circuit schematics: T5 normalizer → Qwen → ERC checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py "LED circuit with 330 ohm resistor" --mock
  python cli.py "solar panel boost converter" --t5-model ./t5-ohmatic --qwen-model ./qwen-ohmatic
  python cli.py "555 astable oscillator" --t5-model google/flan-t5-base --qwen-model org/qwen-ohmatic
        """,
    )
    parser.add_argument("prompt", help="Natural language circuit description (any style)")
    parser.add_argument("--t5-model", default="", help="HF model ID or path for T5 normalizer")
    parser.add_argument("--qwen-model", default="", help="HF model ID or path for Qwen generator")
    parser.add_argument("--temperature", type=float, default=0.2,
                        help="Qwen sampling temperature (default: 0.2)")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Max ERC correction attempts (default: 3)")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock models — no loading, instant output for testing")
    parser.add_argument("--compact", action="store_true", help="Compact JSON output")

    args = parser.parse_args()

    circuit = generate_circuit_cli(
        prompt=args.prompt,
        t5_model_id=args.t5_model,
        qwen_model_id=args.qwen_model,
        temperature=args.temperature,
        max_retries=args.max_retries,
        use_mock=args.mock,
    )

    if not circuit:
        sys.exit(1)

    indent = None if args.compact else 2
    print(json.dumps(circuit, indent=indent))


if __name__ == "__main__":
    main()
