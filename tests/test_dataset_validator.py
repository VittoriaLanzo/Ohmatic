from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

import dataset.validate as validate


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "verifier/config/component_registry.toml"
SCHEMA = ROOT / "shared/schema/circuit_v01.json"


def _minimal_opamp_circuit():
    return {
        "metadata": {
            "title": "Op Amp Pins",
            "description": "Minimal op-amp circuit with signed pin names.",
            "version": "0.1",
            "tags": ["opamp"],
        },
        "components": [
            {
                "id": "VCC1",
                "type": "power_vcc",
                "part": "VCC",
                "value": "5V",
                "pins": {"1": "VCC"},
                "x": 0,
                "y": 0,
            },
            {
                "id": "VEE1",
                "type": "power_vee",
                "part": "VEE",
                "value": "-5V",
                "pins": {"1": "VEE"},
                "x": 10,
                "y": 0,
            },
            {
                "id": "U1",
                "type": "ic_opamp",
                "part": "OPAMP",
                "value": "",
                "pins": {
                    "IN+": "VIN",
                    "IN-": "FB",
                    "OUT": "OUT",
                    "V+": "VCC",
                    "V-": "VEE",
                },
                "x": 20,
                "y": 0,
            },
            {
                "id": "J1",
                "type": "connector",
                "part": "HEADER",
                "value": "",
                "pins": {"VIN": "VIN", "FB": "FB", "OUT": "OUT", "GND": "GND"},
                "x": 30,
                "y": 0,
            },
            {
                "id": "GND1",
                "type": "power_gnd",
                "part": "GND",
                "value": "",
                "pins": {"1": "GND"},
                "x": 40,
                "y": 0,
            },
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.V+"]},
            {"name": "VEE", "pins": ["VEE1.1", "U1.V-"]},
            {"name": "VIN", "pins": ["J1.VIN", "U1.IN+"]},
            {"name": "FB", "pins": ["J1.FB", "U1.IN-"]},
            {"name": "OUT", "pins": ["J1.OUT", "U1.OUT"]},
            {"name": "GND", "pins": ["GND1.1", "J1.GND"]},
        ],
    }


class DatasetValidatorTests(unittest.TestCase):
    def test_registry_types_include_seed_only_types(self):
        types = validate.load_registry_component_types(REGISTRY)

        self.assertIn("power_vee", types)
        self.assertIn("photodiode", types)
        self.assertNotIn("defaults", types)

    def test_schema_enum_matches_registry_types(self):
        registry = validate.load_registry_component_types(REGISTRY)
        schema = validate.load_schema_component_types(SCHEMA)

        self.assertEqual(schema, registry)

    def test_pin_refs_allow_plus_and_minus_when_pins_exist(self):
        errors = validate.validate_circuit(_minimal_opamp_circuit(), registry_path=REGISTRY)

        self.assertEqual(errors, [])

    def test_invalid_pin_ref_is_rejected(self):
        circuit = _minimal_opamp_circuit()
        circuit["nets"][2]["pins"][1] = "U1.NOPE"

        errors = validate.validate_circuit(circuit, registry_path=REGISTRY)

        self.assertTrue(
            any("unknown pin" in error.lower() or "invalid pin" in error.lower() for error in errors),
            errors,
        )

    def test_forbidden_supplier_bom_fields_are_rejected(self):
        circuit = _minimal_opamp_circuit()
        circuit["bom"] = [{"supplier": "example"}]

        errors = validate.validate_circuit(circuit, registry_path=REGISTRY)

        self.assertTrue(any("bom" in error.lower() for error in errors), errors)
        self.assertTrue(any("supplier" in error.lower() for error in errors), errors)

    def test_mpn_related_fields_are_rejected(self):
        circuit = _minimal_opamp_circuit()
        circuit["mpn_found"] = "OPA-example"

        errors = validate.validate_circuit(circuit, registry_path=REGISTRY)

        self.assertTrue(any("mpn_found" in error for error in errors), errors)

    def test_camelcase_supplier_price_and_api_fields_are_rejected(self):
        circuit = _minimal_opamp_circuit()
        circuit["metadata"]["supplierName"] = "example"
        circuit["metadata"]["priceUsd"] = "1.23"
        circuit["apiKey"] = "secret"
        circuit["octopart"] = {"url": "https://example.invalid"}

        errors = validate.validate_circuit(circuit, registry_path=REGISTRY)

        self.assertTrue(any("supplierName" in error for error in errors), errors)
        self.assertTrue(any("priceUsd" in error for error in errors), errors)
        self.assertTrue(any("apiKey" in error for error in errors), errors)
        self.assertTrue(any("octopart" in error for error in errors), errors)

    def test_forbidden_field_matcher_does_not_reject_pin_names(self):
        circuit = _minimal_opamp_circuit()
        circuit["components"][3]["pins"] = {"KEY": "KEY_NET", "URL": "URL_NET", "OUT": "OUT", "GND": "GND"}
        circuit["nets"][2] = {"name": "KEY_NET", "pins": ["J1.KEY", "U1.IN+"]}
        circuit["nets"][3] = {"name": "URL_NET", "pins": ["J1.URL", "U1.IN-"]}
        circuit["nets"][5] = {"name": "GND", "pins": ["GND1.1", "J1.GND"]}

        errors = validate.validate_circuit(circuit, registry_path=REGISTRY)

        self.assertEqual(errors, [])

    def test_registry_entries_have_parts_list_metadata(self):
        missing = validate.check_registry_parts_metadata(REGISTRY)

        self.assertEqual(missing, [])

    def test_cli_accepts_valid_circuit(self):
        result = _run_validator_cli([_minimal_opamp_circuit()])

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Validation: 1/1 circuits valid", result.stdout)

    def test_cli_rejects_expected_hard_failure(self):
        circuit = _minimal_opamp_circuit()
        circuit["nets"][2]["pins"][1] = "U1.NOPE"

        result = _run_validator_cli([circuit])

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("references unknown pin NOPE on U1", result.stdout)

    def test_cli_rejects_forbidden_supplier_bom_fields(self):
        circuit = _minimal_opamp_circuit()
        circuit["bom"] = [{"supplier": "example"}]

        result = _run_validator_cli([circuit])

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("forbidden field at $.bom", result.stdout)
        self.assertIn("forbidden field at $.bom[0].supplier", result.stdout)


def _run_validator_cli(circuits):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "circuits.json"
        path.write_text(json.dumps(circuits), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / "dataset/validate.py"), str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
