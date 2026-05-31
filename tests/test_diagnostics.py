import json
import tempfile
import unittest
from pathlib import Path

from dataset import validate
from eval import diagnostics


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "verifier/config/component_registry.toml"


class DiagnosticsTests(unittest.TestCase):
    def test_unknown_component_diagnostic_is_informative(self):
        bad = {
            "metadata": {"title": "Bad", "description": "Bad component", "version": "0.1", "tags": ["bad"]},
            "components": [
                {"id": "X1", "type": "not_a_component", "part": "", "value": "", "pins": {"1": "N1"}, "x": 0, "y": 0}
            ],
            "nets": [{"name": "N1", "pins": ["X1.1"]}],
        }

        report = diagnostics.analyze_schematic(bad)

        item = report["diagnostics"][0]
        self.assertEqual(item["code"], "REGISTRY_UNKNOWN_COMPONENT_TYPE")
        self.assertEqual(item["severity"], "error")
        self.assertEqual(item["path"], "$.components[0].type")
        self.assertIn("not_a_component", item["message"])
        self.assertTrue(item["why_it_matters"])
        self.assertTrue(item["repair_hint"])
        self.assertEqual(item["related_rule"], "T1-PARSE-REGISTRY")

    def test_malfunctioning_led_without_resistor_has_component_context(self):
        report = diagnostics.analyze_fixture("led_without_resistor")
        items = {item["code"]: item for item in report["diagnostics"]}

        self.assertIn("INTERACTION_LED_MISSING_CURRENT_LIMIT", items)
        item = items["INTERACTION_LED_MISSING_CURRENT_LIMIT"]
        self.assertEqual(item["component_id"], "D1")
        self.assertEqual(item["component_type"], "led")
        self.assertEqual(item["pin_ref"], "D1.A")
        self.assertEqual(item["net_name"], "VCC")
        self.assertEqual(item["related_rule"], "T3-02")
        self.assertIn("led", item["related_component_cards"])
        self.assertIn("resistor", item["related_component_cards"])

    def test_model_feedback_is_compact_and_actionable(self):
        report = diagnostics.analyze_fixture("led_without_resistor")

        feedback = diagnostics.build_retry_feedback(report)

        self.assertEqual(feedback["format"], "ohmatic_diagnostic_feedback_v1")
        self.assertFalse(feedback["valid"])
        self.assertEqual(feedback["repairs"][0]["code"], "INTERACTION_LED_MISSING_CURRENT_LIMIT")
        self.assertIn("repair_hint", feedback["repairs"][0])
        text = json.dumps(feedback)
        self.assertNotIn("```", text)
        self.assertNotIn("<think>", text)
        self.assertNotIn('"components"', text)
        self.assertNotIn('"nets"', text)

    def test_short_between_vcc_and_ground_has_erc_diagnostic(self):
        report = diagnostics.analyze_fixture("short_vcc_gnd")
        codes = {item["code"] for item in report["diagnostics"]}

        self.assertIn("POWER_SHORT_VCC_GND", codes)

    def test_floating_mosfet_gate_has_erc_diagnostic(self):
        report = diagnostics.analyze_fixture("floating_mosfet_gate")
        items = {item["code"]: item for item in report["diagnostics"]}

        self.assertIn("INTERACTION_FLOATING_MOSFET_GATE", items)
        self.assertEqual(items["INTERACTION_FLOATING_MOSFET_GATE"]["related_rule"], "T3-03")
        self.assertIn("resistor", items["INTERACTION_FLOATING_MOSFET_GATE"]["related_component_cards"])

    def test_missing_ic_bypass_and_vcc_net_have_erc_diagnostics(self):
        report = diagnostics.analyze_fixture("ic_without_vcc_bypass")
        codes = {item["code"] for item in report["diagnostics"]}

        self.assertIn("POWER_IC_MISSING_BYPASS_CAPACITOR", codes)

        missing_vcc = diagnostics.analyze_fixture("ic_not_on_literal_vcc")
        missing_codes = {item["code"] for item in missing_vcc["diagnostics"]}
        self.assertIn("POWER_IC_MISSING_LITERAL_VCC_NET", missing_codes)

    def test_reversed_capacitor_and_button_without_pull_have_erc_diagnostics(self):
        cap_report = diagnostics.analyze_fixture("reversed_capacitor")
        cap_codes = {item["code"] for item in cap_report["diagnostics"]}
        self.assertIn("POLARITY_REVERSED_CAPACITOR", cap_codes)

        button_report = diagnostics.analyze_fixture("button_without_pull")
        button_codes = {item["code"] for item in button_report["diagnostics"]}
        self.assertIn("INTERACTION_BUTTON_MISSING_PULL_RESISTOR", button_codes)

    def test_isolated_component_has_erc_diagnostic(self):
        report = diagnostics.analyze_fixture("isolated_component")
        codes = {item["code"] for item in report["diagnostics"]}

        self.assertIn("CONNECTIVITY_COMPONENT_NOT_REACHABLE_FROM_POWER", codes)

    def test_forbidden_supplier_field_gets_dedicated_diagnostic(self):
        circuit = _minimal_valid_circuit()
        circuit["components"][2]["supplier"] = "example"

        report = diagnostics.analyze_schematic(circuit)
        codes = {item["code"] for item in report["diagnostics"]}

        self.assertIn("FORBIDDEN_SUPPLIER_FIELD", codes)

    def test_invalid_pin_ref_diagnostic_includes_path_and_expected_pin_names(self):
        circuit = _minimal_valid_circuit()
        circuit["nets"][1]["pins"][1] = "U1.NOPE"

        report = diagnostics.analyze_schematic(circuit)
        pin_items = [item for item in report["diagnostics"] if item["code"] == "PIN_UNKNOWN_FOR_COMPONENT"]

        self.assertEqual(len(pin_items), 1)
        self.assertEqual(pin_items[0]["path"], "$.nets[1].pins[1]")
        self.assertIn("V+", pin_items[0]["expected"])
        self.assertEqual(pin_items[0]["actual"], "NOPE")

    def test_valid_circuit_has_empty_diagnostics(self):
        report = diagnostics.analyze_schematic(_minimal_valid_circuit())

        self.assertEqual(report["diagnostics"], [])
        self.assertTrue(report["valid"])

    def test_taxonomy_covers_all_registry_component_types(self):
        coverage = diagnostics.coverage_report()
        registry = validate.load_registry_component_types(REGISTRY)

        self.assertEqual(set(coverage["component_type_coverage"]), registry)
        self.assertEqual(coverage["missing_component_types"], [])

    def test_cli_writes_coverage_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "diagnostic_coverage.json"
            result = diagnostics.main(["--taxonomy", str(ROOT / "eval/error_taxonomy.json"), "--coverage-report", str(out)])

            self.assertEqual(result, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["missing_component_types"], [])


def _minimal_valid_circuit():
    return {
        "metadata": {
            "title": "Buffered Reference",
            "description": "A small valid op-amp buffer with bypassing.",
            "version": "0.1",
            "tags": ["fixture"],
        },
        "components": [
            {"id": "VCC1", "type": "power_vcc", "part": "VCC", "value": "5V", "pins": {"1": "VCC"}, "x": 0, "y": 0},
            {"id": "GND1", "type": "power_gnd", "part": "GND", "value": "0V", "pins": {"1": "GND"}, "x": 0, "y": 80},
            {"id": "U1", "type": "ic_opamp", "part": "SOIC-8", "value": "buffer", "pins": {"IN+": "VIN", "IN-": "OUT", "OUT": "OUT", "V+": "VCC", "V-": "GND"}, "x": 80, "y": 40},
            {"id": "C1", "type": "capacitor", "part": "0603", "value": "100nF", "pins": {"1": "VCC", "2": "GND"}, "x": 40, "y": 35},
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "U1.V+", "C1.1"]},
            {"name": "OUT", "pins": ["U1.IN+", "U1.IN-", "U1.OUT"]},
            {"name": "GND", "pins": ["GND1.1", "U1.V-", "C1.2"]},
        ],
    }


if __name__ == "__main__":
    unittest.main()
