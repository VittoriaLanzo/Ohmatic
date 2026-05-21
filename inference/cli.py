#!/usr/bin/env python3
"""
Command-line interface for circuit generation.
Usage: ohmatic "describe your circuit" [--model path/to/model.gguf]
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

# Ensure project root is in sys.path so cross-package imports work whether
# this script is invoked as `python inference/cli.py` or `python cli.py`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from inference.model import load_model


def generate_circuit_cli(
    prompt: str,
    model_path: Path | None = None,
    temperature: float = 0.7,
    use_mock: bool = False,
    validate: bool = True,
) -> Dict[str, Any] | None:
    """
    Generate circuit from command-line prompt.

    Args:
        prompt: Natural language circuit description
        model_path: Path to GGUF model
        temperature: Sampling temperature
        use_mock: Use mock model for testing
        validate: Whether to validate output

    Returns:
        Generated circuit dict or None
    """
    # Load model
    model = load_model(model_path, use_mock=use_mock)
    print(f"Using model: {model}", file=sys.stderr)

    # Generate
    print("Generating circuit...", file=sys.stderr)
    circuit = model.generate_circuit(prompt, temperature=temperature)

    if not circuit:
        print("Error: Failed to generate circuit", file=sys.stderr)
        return None

    # Validate if requested
    if validate:
        from dataset.validate import SchemaValidator  # noqa: PLC0415
        validator = SchemaValidator()
        if not validator.validate_circuit(circuit):
            print("Warning: Generated circuit failed validation:", file=sys.stderr)
            for err in validator.get_errors()[:3]:
                print(f"  - {err}", file=sys.stderr)
            # Still return it, user can see the errors

    return circuit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate circuit schematics using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py "LED circuit with 330 ohm resistor"
  python cli.py "OpAmp inverting amplifier" --model model.gguf --temperature 0.5
  python cli.py "555 timer oscillator" --mock
        """,
    )
    parser.add_argument(
        "prompt",
        help="Natural language description of circuit to generate",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help="Path to GGUF model file (uses mock if not provided)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Sampling temperature (0.0-1.0, default: 0.7)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock model for testing",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip validation of output",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Compact JSON output",
    )

    args = parser.parse_args()

    # Generate circuit
    circuit = generate_circuit_cli(
        prompt=args.prompt,
        model_path=args.model,
        temperature=args.temperature,
        use_mock=args.mock,
        validate=not args.no_validate,
    )

    if not circuit:
        sys.exit(1)

    # Output
    indent = None if args.compact else 2
    output = json.dumps(circuit, indent=indent)
    print(output)


if __name__ == "__main__":
    main()
