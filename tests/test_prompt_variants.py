"""Tests for dataset/generate_prompts.py — deterministic prompt variant builder."""

import unittest

from dataset import generate_prompts


class PromptVariantTests(unittest.TestCase):
    def test_prompt_variants_do_not_include_circuit_json(self):
        record = {
            "id": "circuit-1",
            "nl_prompts": [{"text": "Build a 5V LED indicator with a 330 ohm resistor."}],
            "family": "led_driver",
            "component_count": 5,
            "topology_tags": ["indicator"],
        }

        variants = generate_prompts.build_prompt_variants(record, count=4)

        for variant in variants:
            self.assertNotIn('"components"', variant["text"])
            self.assertNotIn('"nets"', variant["text"])
            self.assertNotIn("```", variant["text"])
            self.assertNotIn("<think>", variant["text"])

    def test_prompt_variants_link_to_record_id(self):
        record = {
            "id": "circuit-1",
            "nl_prompts": [{"text": "Build a 5V LED indicator with a 330 ohm resistor."}],
            "family": "led_driver",
            "component_count": 5,
            "topology_tags": ["indicator"],
        }

        variants = generate_prompts.build_prompt_variants(record, count=3)

        self.assertEqual(len(variants), 3)
        for variant in variants:
            self.assertEqual(variant["record_id"], "circuit-1")
            self.assertTrue(variant["text"])
            self.assertTrue(variant["t5_input"].startswith("normalize ohmatic request: "))

    def test_prompt_variants_cover_precision_levels(self):
        record = {
            "id": "manual_teacher_example",
            "family": "led_driver",
            "topology_tags": ["indicator"],
            "nl_prompts": [{"text": "5V LED indicator with 330R resistor."}],
        }

        variants = generate_prompts.build_prompt_variants(record, count=4)

        levels = {v["precision_level"] for v in variants}
        self.assertGreaterEqual(len(levels), 3)

    def test_prompt_variants_fall_back_to_family_name_without_nl_prompts(self):
        record = {
            "id": "fallback-test",
            "family": "power_conditioning",
            "topology_tags": ["regulator"],
        }

        variants = generate_prompts.build_prompt_variants(record, count=2)

        self.assertEqual(len(variants), 2)
        for variant in variants:
            self.assertTrue(variant["text"])


if __name__ == "__main__":
    unittest.main()
