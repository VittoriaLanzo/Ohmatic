import unittest
from unittest.mock import Mock, patch

from inference import t5_normalizer


class T5PromptHelperTests(unittest.TestCase):
    def test_build_t5_input_uses_helper_prefix(self):
        source = t5_normalizer.build_t5_input("  make a 5V led blinker  ")

        self.assertEqual(source, "normalize ohmatic request: make a 5V led blinker")

    def test_static_helper_output_is_not_circuit_json(self):
        helper = t5_normalizer.StaticT5Normalizer()
        output = helper.normalize("make a 5V led blinker")

        self.assertTrue(output.startswith("ohmatic_intent_v1 | "))
        self.assertIn("raw_request=make a 5V led blinker", output)
        self.assertNotIn('"components"', output)
        self.assertNotIn('"nets"', output)
        self.assertNotIn("<think>", output)
        self.assertNotIn("```", output)

    def test_t5_helper_defaults_to_flan_t5_base(self):
        self.assertEqual(t5_normalizer.T5_MODEL_ID, "google/flan-t5-base")

    def test_t5_helper_rejects_final_circuit_json_output(self):
        with self.assertRaisesRegex(ValueError, "must not emit final circuit JSON"):
            t5_normalizer.validate_helper_text('{"components":[],"nets":[]}')

    def test_t5_helper_loads_huggingface_seq2seq_model_lazily(self):
        tokenizer = Mock()
        tokenizer.return_value = {"input_ids": Mock(to=Mock(return_value="ids"))}
        tokenizer.decode.return_value = "ohmatic_intent_v1 | focus=indicator"
        model = Mock()
        model.device = "cpu"
        model.generate.return_value = ["tokens"]

        with patch.object(t5_normalizer, "AutoTokenizer") as auto_tokenizer, patch.object(
            t5_normalizer, "AutoModelForSeq2SeqLM"
        ) as auto_model:
            auto_tokenizer.from_pretrained.return_value = tokenizer
            auto_model.from_pretrained.return_value = model
            helper = t5_normalizer.T5Normalizer()

            output = helper.normalize("make a led circuit")

        auto_tokenizer.from_pretrained.assert_called_once_with("google/flan-t5-base")
        auto_model.from_pretrained.assert_called_once_with("google/flan-t5-base")
        tokenizer.assert_called_once_with("normalize ohmatic request: make a led circuit", return_tensors="pt")
        model.generate.assert_called_once()
        self.assertEqual(output, "ohmatic_intent_v1 | focus=indicator")


if __name__ == "__main__":
    unittest.main()
