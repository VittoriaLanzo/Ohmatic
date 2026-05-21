#!/usr/bin/env python3
"""
Validate circuit schematics against schema v0.1.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


VALID_COMPONENT_TYPES = {
    "resistor", "capacitor", "led", "diode", "transistor_npn", "transistor_pnp",
    "mosfet_n", "mosfet_p", "ic_timer", "ic_opamp", "ic_regulator", "ic_logic",
    "ic_mcu", "ic_driver", "power_vcc", "power_gnd", "connector", "crystal",
    "inductor", "button", "speaker", "sensor"
}


class SchemaValidator:
    """Validates circuit JSON against schema v0.1."""

    def __init__(self) -> None:
        self.errors: List[str] = []

    def validate_circuit(self, circuit: Dict[str, Any]) -> bool:
        """Validate a complete circuit. Returns True if valid."""
        self.errors.clear()

        # Validate metadata
        if "metadata" not in circuit:
            self.errors.append("Missing 'metadata' field")
            return False
        self._validate_metadata(circuit["metadata"])

        # Validate components
        if "components" not in circuit:
            self.errors.append("Missing 'components' field")
            return False
        components = circuit["components"]
        if not isinstance(components, list) or len(components) == 0:
            self.errors.append("'components' must be a non-empty list")
            return False
        self._validate_components(components)

        # Validate nets
        if "nets" not in circuit:
            self.errors.append("Missing 'nets' field")
            return False
        nets = circuit["nets"]
        if not isinstance(nets, list) or len(nets) == 0:
            self.errors.append("'nets' must be a non-empty list")
            return False
        self._validate_nets(nets, components)

        return len(self.errors) == 0

    def _validate_metadata(self, metadata: Dict[str, Any]) -> None:
        """Validate metadata section."""
        required = {"title", "description", "version", "tags"}
        if not all(k in metadata for k in required):
            self.errors.append(f"metadata missing required fields: {required}")
        if metadata.get("version") != "0.1":
            self.errors.append(f"version must be '0.1', got '{metadata.get('version')}'")
        if not isinstance(metadata.get("tags"), list):
            self.errors.append("metadata.tags must be a list")

    def _validate_components(self, components: List[Dict[str, Any]]) -> None:
        """Validate components array."""
        seen_ids: Set[str] = set()
        for i, comp in enumerate(components):
            comp_id = comp.get("id")
            if not comp_id:
                self.errors.append(f"component[{i}] missing 'id'")
                continue
            if comp_id in seen_ids:
                self.errors.append(f"Duplicate component id: {comp_id}")
            seen_ids.add(comp_id)

            # Check required fields
            for field in ["type", "pins", "x", "y"]:
                if field not in comp:
                    self.errors.append(f"component '{comp_id}' missing '{field}'")

            # Validate type
            comp_type = comp.get("type")
            if comp_type not in VALID_COMPONENT_TYPES:
                self.errors.append(f"component '{comp_id}' invalid type: {comp_type}")

            # Validate pins is dict
            pins = comp.get("pins", {})
            if not isinstance(pins, dict):
                self.errors.append(f"component '{comp_id}' pins must be dict")

    def _validate_nets(self, nets: List[Dict[str, Any]], components: List[Dict[str, Any]]) -> None:
        """Validate nets and connectivity."""
        # Build component pin map
        comp_pins: Dict[str, Set[str]] = {}
        for comp in components:
            comp_id = comp.get("id")
            if comp_id:
                comp_pins[comp_id] = set(comp.get("pins", {}).keys())

        # Track which pins are used
        used_pins: Set[str] = set()
        vcc_found = False
        gnd_found = False

        for i, net in enumerate(nets):
            net_name = net.get("name")
            pins = net.get("pins", [])

            if not net_name:
                self.errors.append(f"net[{i}] missing 'name'")
            if not isinstance(pins, list) or len(pins) < 2:
                self.errors.append(f"net '{net_name}' must have at least 2 pins, got {len(pins)}")

            # Track VCC/GND
            if net_name == "VCC":
                vcc_found = True
            if net_name == "GND":
                gnd_found = True

            # Validate pin references
            for pin_ref in pins:
                if not isinstance(pin_ref, str) or "." not in pin_ref:
                    self.errors.append(f"net '{net_name}' invalid pin ref: {pin_ref}")
                    continue

                comp_id, pin_num = pin_ref.split(".", 1)
                if comp_id not in comp_pins:
                    self.errors.append(f"net '{net_name}' references unknown component: {comp_id}")
                elif pin_num not in comp_pins[comp_id]:
                    self.errors.append(f"net '{net_name}' references unknown pin {pin_num} on {comp_id}")
                else:
                    used_pins.add(pin_ref)

        # Check required nets
        if not vcc_found:
            self.errors.append("Missing required 'VCC' net")
        if not gnd_found:
            self.errors.append("Missing required 'GND' net")

        # Check all component pins are used
        for comp in components:
            comp_id = comp.get("id")
            for pin_id in comp.get("pins", {}).keys():
                pin_ref = f"{comp_id}.{pin_id}"
                if pin_ref not in used_pins:
                    self.errors.append(f"component pin {pin_ref} not connected to any net")

    def get_errors(self) -> List[str]:
        """Return list of validation errors."""
        return self.errors


def load_examples(file_path: Path) -> List[Dict[str, Any]]:
    """Load examples from JSON file."""
    with open(file_path, "r") as f:
        return json.load(f)


def validate_file(file_path: Path) -> Tuple[int, int]:
    """Validate all circuits in a file. Returns (total, valid)."""
    examples = load_examples(file_path)
    validator = SchemaValidator()
    valid_count = 0

    for i, circuit in enumerate(examples):
        if validator.validate_circuit(circuit):
            valid_count += 1
        else:
            print(f"Circuit {i}: {circuit.get('metadata', {}).get('title', 'UNKNOWN')}")
            for error in validator.get_errors():
                print(f"  - {error}")

    return len(examples), valid_count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate.py <examples.json>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Error: {file_path} not found")
        sys.exit(1)

    total, valid = validate_file(file_path)
    print(f"\nValidation: {valid}/{total} circuits valid")
    sys.exit(0 if valid == total else 1)
