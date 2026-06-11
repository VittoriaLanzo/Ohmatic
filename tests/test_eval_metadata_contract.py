import json

from eval.benchmark import prod_eval, verify_model


def test_verify_model_report_metadata_names_parser_helper_and_constraint():
    metadata = verify_model.eval_contract_metadata()

    assert metadata == {
        "model_track": "qwen3_parser",
        "prompt_helper": "t5_normalized",
        "decoder_constraint": "none",
    }


def test_prod_eval_summary_metadata_names_parser_helper_and_constraint(tmp_path, monkeypatch):
    class FakeResult:
        ok = True
        attempts = 1

    class FakePipeline:
        @classmethod
        def from_config(cls, _cfg):
            return cls()

        def run(self, _prompt):
            return FakeResult()

    out_path = tmp_path / "prod_eval.json"
    monkeypatch.setattr(prod_eval, "_load_items", lambda *_args: [{"id": "case-1", "prompt": "blink led", "partition": "smoke"}])
    monkeypatch.setattr(prod_eval, "OhmaticPipeline", FakePipeline)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prod_eval.py",
            "--adapter",
            "local-adapter",
            "--n",
            "1",
            "--max-shots",
            "1",
            "--out",
            str(out_path),
        ],
    )

    prod_eval.main()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["summary"]["model_track"] == "qwen3_parser"
    assert payload["summary"]["prompt_helper"] == "t5_normalized"
    assert payload["summary"]["decoder_constraint"] == "none"
