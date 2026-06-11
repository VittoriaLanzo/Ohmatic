from enricher.stub.server import build_enrich_http_response, build_enrich_response
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _circuit():
    return {
        "metadata": {"title": "Enrich", "description": "local", "version": "0.1", "tags": ["parts"]},
        "components": [
            {
                "id": "R1",
                "type": "resistor",
                "value": "330",
                "part": "0603",
                "x": 0,
                "y": 0,
                "pins": {"1": "VCC", "2": "OUT"},
            },
            {
                "id": "VCC1",
                "type": "power_vcc",
                "value": "5V",
                "part": "VCC",
                "x": 10,
                "y": 0,
                "pins": {"1": "VCC"},
            },
        ],
        "nets": [{"name": "VCC", "pins": ["VCC1.1", "R1.1"]}],
    }


def test_enricher_stub_returns_local_parts_list_rows_without_supplier_fields():
    rows = build_enrich_response(_circuit())

    assert [row["id"] for row in rows] == ["R1", "VCC1"]
    assert rows[0]["buyable"] is True
    assert rows[1]["buyable"] is False

    forbidden = {"supplier", "price_usd", "stock", "url", "affiliate_url", "api_key", "mpn", "mpn_found"}
    for row in rows:
        assert forbidden.isdisjoint(row)


def test_enricher_stub_returns_structured_error_when_parts_list_fails():
    circuit = _circuit()
    circuit["components"][0]["type"] = "unknown_widget"

    status, response = build_enrich_http_response(circuit)

    assert status == 422
    assert response["error"] == "parts_list_failed"
    assert "unknown component type" in response["message"]


def test_enrich_contract_documents_parts_list_error_response():
    text = (ROOT / "shared/docs/contracts.md").read_text(encoding="utf-8")
    enrich_section = text.split("POST /enrich", 1)[1]

    assert "Response 422" in enrich_section
    assert "parts_list_failed" in enrich_section
