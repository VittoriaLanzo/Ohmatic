#!/usr/bin/env python3
"""
Gradio web UI for Ohmatic circuit generator.
Usage: python app.py [--model path/to/model.gguf] [--share]
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import gradio as gr

# Ensure project root is importable whether invoked as `python ui/app.py` or
# `python app.py` from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from inference.model import load_model
from ui.renderer import SchematicRenderer
from dataset.validate import SchemaValidator


class OhmaticApp:
    """Gradio app for circuit generation."""

    def __init__(self, model_path: Optional[Path] = None, use_mock: bool = True) -> None:
        self.model = load_model(model_path, use_mock=use_mock)
        self.renderer = SchematicRenderer()
        self.examples = self._load_examples()

    def _load_examples(self) -> list:
        """Load example circuits from dataset."""
        examples_file = Path("dataset/examples.json")
        if examples_file.exists():
            with open(examples_file, "r") as f:
                return json.load(f)
        return []

    def _format_hackatime(self, dt: datetime) -> str:
        """Format a datetime in hackatime style."""
        return f"{dt.hour:02d}:{dt.minute:02d} hackatime"

    def generate(self, prompt: str, temperature: float = 0.7) -> Tuple[str, Optional[str], str]:
        """
        Generate circuit from prompt.

        Returns:
            (json_output, svg_output, status_message)
        """
        if not prompt.strip():
            return "", None, "Error: Please enter a circuit description"

        try:
            circuit = self.model.generate_circuit(prompt, temperature=temperature)

            if not circuit:
                return "", None, "Error: Failed to generate circuit"

            # Format JSON
            json_output = json.dumps(circuit, indent=2)

            # Render to SVG
            svg_output = self.renderer.render(circuit)
            status_time = self._format_hackatime(datetime.now())

            return json_output, svg_output, f"✓ Circuit generated successfully at {status_time}"

        except Exception as e:
            return "", None, f"Error: {str(e)}"

    def validate_json(self, json_text: str) -> str:
        """Validate JSON against schema."""
        if not json_text.strip():
            return "Error: No JSON to validate"

        try:
            circuit = json.loads(json_text)
            validator = SchemaValidator()
            if validator.validate_circuit(circuit):
                return "✓ Valid circuit!"
            errors = validator.get_errors()
            error_text = "\n".join(f"• {e}" for e in errors[:10])
            return f"✗ Validation failed:\n{error_text}"

        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON - {str(e)}"

    def render_example(self, example_idx: int) -> Tuple[str, str, str]:
        """Load and render an example circuit."""
        if not self.examples or example_idx >= len(self.examples):
            return "", "", "No examples available"

        circuit = self.examples[example_idx]
        json_output = json.dumps(circuit, indent=2)
        svg_output = self.renderer.render(circuit)
        title = circuit.get("metadata", {}).get("title", "Circuit")
        loaded_time = self._format_hackatime(datetime.now())

        return json_output, svg_output, f"✓ Loaded: {title} at {loaded_time}"

    def build_interface(self) -> gr.Blocks:
        """Build Gradio interface."""
        with gr.Blocks(
            title="Ohmatic - AI Circuit Generator",
            theme=gr.themes.Soft(),
        ) as app:
            gr.Markdown("""
            # Ohmatic: AI-Powered Circuit Schematic Generator
            
            Generate circuit schematics using natural language descriptions. 
            Runs fully locally with no cloud dependencies.
            """)

            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Generate Circuit")

                    prompt = gr.Textbox(
                        label="Circuit Description",
                        placeholder="E.g., 'LED circuit with 330 ohm current limiting resistor'",
                        lines=3,
                    )

                    temperature = gr.Slider(
                        label="Temperature",
                        minimum=0.0,
                        maximum=1.0,
                        value=0.7,
                        step=0.1,
                        info="Lower = deterministic, Higher = creative",
                    )

                    generate_btn = gr.Button("Generate Circuit", scale=0, variant="primary")

                    status = gr.Textbox(
                        label="Status",
                        interactive=False,
                        lines=2,
                    )

                with gr.Column(scale=1):
                    gr.Markdown("### Generated Circuit")

                    json_output = gr.Code(
                        language="json",
                        label="Circuit JSON (v0.1)",
                        interactive=True,
                    )

                    validate_btn = gr.Button("Validate JSON")
                    validation_result = gr.Textbox(
                        label="Validation Result",
                        interactive=False,
                        lines=2,
                    )

            with gr.Row():
                svg_output = gr.HTML(label="Schematic (SVG)")

            with gr.Row():
                gr.Markdown("### Load Example Circuits")

                example_select = gr.Dropdown(
                    label="Examples",
                    choices=[
                        (f"{i}: {ex.get('metadata', {}).get('title', 'Circuit')}", i)
                        for i, ex in enumerate(self.examples)
                    ],
                    value=0 if self.examples else None,
                )

                load_example_btn = gr.Button("Load Example")
                example_status = gr.Textbox(
                    label="Status",
                    interactive=False,
                )

            with gr.Row():
                gr.Markdown("### About")
                gr.Markdown("""
                **Ohmatic** fine-tunes Qwen2.5-3B using QLoRA to generate valid circuit schematics as JSON.
                
                **Features:**
                - Offline inference (llama-cpp-python)
                - Schema validation (v0.1)
                - SVG rendering
                - Batch generation via API
                
                **Schema:**
                - Components with pins, values, positions
                - Nets connecting component pins
                - Metadata (title, description, tags)
                
                [GitHub](https://github.com/...)
                """)

            # Connect events
            generate_btn.click(
                self.generate,
                inputs=[prompt, temperature],
                outputs=[json_output, svg_output, status],
            )

            validate_btn.click(
                self.validate_json,
                inputs=[json_output],
                outputs=[validation_result],
            )

            load_example_btn.click(
                self.render_example,
                inputs=[example_select],
                outputs=[json_output, svg_output, example_status],
            )

        return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Ohmatic web UI")
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help="Path to GGUF model file",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Share public link",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run on",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to",
    )

    args = parser.parse_args()

    # Create app
    ohmatic_app = OhmaticApp(model_path=args.model)
    interface = ohmatic_app.build_interface()

    # Launch
    interface.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        show_error=True,
    )


if __name__ == "__main__":
    main()
