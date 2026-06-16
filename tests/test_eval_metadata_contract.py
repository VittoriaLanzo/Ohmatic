import json
import os

import pytest

from eval.benchmark import prod_eval


@pytest.mark.skipif(os.name == "nt", reason="pytest tmp-factory perms on Windows dev box; runs on Linux")
def test_prod_eval_summary_metadata_names_parser_helper_and_constraint(tmp_path, monkeypatch):
    class FakeResult:
        ok = True
        attempts = 1

    class FakePipeline:
        @classmethod
        def from_config(cls, _cfg):
            return cls()

        def run(self, _prompt, return_trace=False):
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
