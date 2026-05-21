#!/usr/bin/env python3
"""
Render circuit JSON to SVG schematic diagram.
"""
import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class Component:
    """Circuit component."""
    id: str
    type: str
    part: str
    value: str
    pins: Dict[str, str]
    x: float
    y: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Component":
        return cls(
            id=d["id"],
            type=d.get("type", ""),
            part=d.get("part", ""),
            value=d.get("value", ""),
            pins=d.get("pins", {}),
            x=float(d.get("x", 0)),
            y=float(d.get("y", 0)),
        )


class SchematicRenderer:
    """Render circuits to SVG."""

    # Component symbols (width x height in mm)
    COMPONENT_SIZE = 20
    PIN_SPACING = 10
    WIRE_SPACING = 30

    # Symbol definitions for different component types
    SYMBOLS = {
        "resistor": "zigzag",
        "capacitor": "parallel-lines",
        "led": "triangle",
        "diode": "triangle",
        "transistor_npn": "transistor",
        "transistor_pnp": "transistor",
        "mosfet_n": "transistor",
        "mosfet_p": "transistor",
        "ic_timer": "ic",
        "ic_opamp": "ic",
        "ic_regulator": "ic",
        "ic_logic": "ic",
        "ic_mcu": "ic",
        "ic_driver": "ic",
        "power_vcc": "dot",
        "power_gnd": "ground",
        "connector": "dot",
        "crystal": "crystal",
        "inductor": "inductor",
        "button": "switch",
        "speaker": "speaker",
        "sensor": "ic",
    }

    def __init__(self, scale: float = 2.0, margin: float = 20.0) -> None:
        """
        Initialize renderer.

        Args:
            scale: Scale factor for mm to SVG units
            margin: Margin around circuit in SVG units
        """
        self.scale = scale
        self.margin = margin
        self.svg_width = 800
        self.svg_height = 600

    def render(self, circuit: Dict[str, Any]) -> str:
        """
        Render circuit to SVG string.

        Args:
            circuit: Circuit dict with components and nets

        Returns:
            SVG XML string
        """
        components = circuit.get("components", [])
        nets = circuit.get("nets", [])
        metadata = circuit.get("metadata", {})

        # Parse components
        comps = {c["id"]: Component.from_dict(c) for c in components}

        # Calculate bounds
        if comps:
            xs = [c.x for c in comps.values()]
            ys = [c.y for c in comps.values()]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
        else:
            min_x = min_y = 0
            max_x = max_y = 100

        # Add padding
        width = (max_x - min_x + 50) * self.scale + 2 * self.margin
        height = (max_y - min_y + 50) * self.scale + 2 * self.margin

        svg = StringIO()

        # SVG header
        svg.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n')
        svg.write('<style>text { font-family: monospace; font-size: 10px; } .net-label { font-size: 8px; } .component-label { font-size: 9px; font-weight: bold; }</style>\n')

        # Title
        if metadata.get("title"):
            svg.write(f'<text x="10" y="20" class="title">{metadata["title"]}</text>\n')

        # Transform to viewport
        svg.write(f'<g transform="translate({self.margin}, {self.margin}) scale({self.scale})">\n')

        # Draw nets first (background)
        self._draw_nets(svg, nets, comps, min_x, min_y)

        # Draw components
        for comp in comps.values():
            self._draw_component(svg, comp)

        svg.write('</g>\n')
        svg.write('</svg>\n')

        return svg.getvalue()

    def _draw_component(self, svg: StringIO, comp: Component) -> None:
        """Draw a single component."""
        x, y = comp.x, comp.y
        size = self.COMPONENT_SIZE

        # Component box
        svg.write(f'<rect x="{x-size/2}" y="{y-size/2}" width="{size}" height="{size}" ')
        svg.write('fill="white" stroke="black" stroke-width="1"/>\n')

        # Component label
        label = f"{comp.id}"
        svg.write(f'<text x="{x}" y="{y}" text-anchor="middle" dominant-baseline="middle" ')
        svg.write(f'class="component-label">{label}</text>\n')

        # Pin markers
        num_pins = len(comp.pins)
        if num_pins <= 2:
            # Horizontal pins
            svg.write(f'<circle cx="{x-size/2-5}" cy="{y}" r="2" fill="red"/>\n')
            svg.write(f'<circle cx="{x+size/2+5}" cy="{y}" r="2" fill="red"/>\n')
        else:
            # Pins around box
            pins_per_side = (num_pins + 3) // 4
            for i, pin_id in enumerate(sorted(comp.pins.keys())):
                if i % 2 == 0:
                    px = x - size / 2 - 5
                    py = y - size / 4 + (i % 4) * size / 4
                else:
                    px = x + size / 2 + 5
                    py = y - size / 4 + (i % 4) * size / 4
                svg.write(f'<circle cx="{px}" cy="{py}" r="1.5" fill="red"/>\n')

    def _draw_nets(
        self, svg: StringIO, nets: List[Dict[str, Any]], comps: Dict[str, Component],
        min_x: float, min_y: float
    ) -> None:
        """Draw nets (connections between components)."""
        net_colors = {}
        colors = ["blue", "green", "purple", "orange", "brown", "cyan", "magenta"]

        for net_idx, net in enumerate(nets):
            net_name = net.get("name", f"Net{net_idx}")
            pins = net.get("pins", [])

            if len(pins) < 2:
                continue

            color = colors[net_idx % len(colors)]
            net_colors[net_name] = color

            # Draw connections between pins in this net
            positions = []
            for pin_ref in pins:
                if "." not in pin_ref:
                    continue
                comp_id, pin_num = pin_ref.split(".", 1)
                if comp_id in comps:
                    comp = comps[comp_id]
                    positions.append((comp.x, comp.y, pin_ref))

            # Draw polyline connecting all pins in net
            if positions:
                path_points = " ".join(f"{p[0]},{p[1]}" for p in positions)
                svg.write(f'<polyline points="{path_points}" stroke="{color}" stroke-width="0.5" fill="none" opacity="0.5"/>\n')

                # Net label at first position
                if positions:
                    x, y = positions[0][0], positions[0][1]
                    svg.write(f'<text x="{x+5}" y="{y-5}" class="net-label" fill="{color}">{net_name}</text>\n')

    def render_to_file(self, circuit: Dict[str, Any], output_path: Path) -> None:
        """Render circuit and save to SVG file."""
        svg = self.render(circuit)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(svg)


def render_circuit_file(
    input_json: Path,
    output_svg: Path,
    circuit_index: int = 0,
) -> None:
    """
    Render a circuit from JSON file to SVG.

    Args:
        input_json: Path to examples.json
        output_svg: Output SVG file path
        circuit_index: Which circuit to render (default: 0)
    """
    with open(input_json, "r") as f:
        circuits = json.load(f)

    if circuit_index >= len(circuits):
        raise IndexError(f"Circuit index {circuit_index} out of range ({len(circuits)} circuits)")

    renderer = SchematicRenderer()
    renderer.render_to_file(circuits[circuit_index], output_svg)
    print(f"Rendered circuit {circuit_index} to {output_svg}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render circuits to SVG")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("dataset/examples.json"),
        help="Input examples.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("circuit.svg"),
        help="Output SVG file",
    )
    parser.add_argument(
        "--circuit",
        type=int,
        default=0,
        help="Circuit index to render",
    )

    args = parser.parse_args()

    try:
        render_circuit_file(args.input, args.output, args.circuit)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        exit(1)
