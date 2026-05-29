import unittest
from unittest.mock import Mock, patch

from inference.cli import generate_circuit_cli


VALID_CIRCUIT = {
    "metadata": {
        "title": "Mock",
        "description": "Valid mock circuit",
        "version": "0.1",
        "tags": ["mock"],
    },
    "components": [
        {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
        {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 20},
        {"id": "R1", "type": "resistor", "part": "0603", "value": "10k", "pins": {"1": "VCC", "2": "GND"}, "x": 20, "y": 20},
    ],
    "nets": [
        {"name": "VCC", "pins": ["VCC1.1", "R1.1"]},
        {"name": "GND", "pins": ["GND1.1", "R1.2"]},
    ],
}


class InferenceCliT5HelperTests(unittest.TestCase):
    def test_generate_circuit_cli_bypasses_t5_helper_by_default(self):
        model = Mock()
        model.generate_circuit.return_value = VALID_CIRCUIT
        helper = Mock()

        with patch("inference.cli.load_model", return_value=model):
            circuit = generate_circuit_cli(
                "make a led circuit",
                use_mock=True,
                validate=False,
                normalizer=helper,
            )

        helper.normalize.assert_not_called()
        model.generate_circuit.assert_called_once_with("make a led circuit", temperature=0.7)
        self.assertEqual(circuit, VALID_CIRCUIT)

    def test_generate_circuit_cli_can_opt_into_t5_helper(self):
        model = Mock()
        model.generate_circuit.return_value = VALID_CIRCUIT
        helper = Mock()
        helper.normalize.return_value = "ohmatic_intent_v1 | focus=indicator"

        with patch("inference.cli.load_model", return_value=model):
            circuit = generate_circuit_cli(
                "make a led circuit",
                use_mock=True,
                validate=False,
                use_t5=True,
                normalizer=helper,
            )

        helper.normalize.assert_called_once_with("make a led circuit")
        model.generate_circuit.assert_called_once_with("ohmatic_intent_v1 | focus=indicator", temperature=0.7)
        self.assertEqual(circuit, VALID_CIRCUIT)


if __name__ == "__main__":
    unittest.main()
