from gateway.stub.server import (
    HARDCODED_CIRCUIT,
    build_done_result,
    build_jameco_preflight_gateway_http_response,
    build_procurement_gateway_http_response,
)
from shared.procurement import AvantLinkConfig


def test_gateway_done_result_exposes_required_parts_list():
    result = build_done_result(HARDCODED_CIRCUIT)

    assert "parts_list" in result
    assert [row["id"] for row in result["parts_list"]] == ["R1", "VCC1", "GND1"]
    assert "bom" not in result
    assert result["latency_ms"] == {"inference": 0, "drc": 0, "parts_list": 0}
    assert "bom" not in result["latency_ms"]


def test_gateway_parts_list_marks_power_symbols_not_buyable():
    result = build_done_result(HARDCODED_CIRCUIT)
    by_id = {row["id"]: row for row in result["parts_list"]}

    assert by_id["R1"]["buyable"] is True
    assert by_id["VCC1"]["buyable"] is False
    assert by_id["GND1"]["buyable"] is False


def test_gateway_parts_list_contains_no_supplier_fields():
    result = build_done_result(HARDCODED_CIRCUIT)
    forbidden = {"supplier", "price_usd", "stock", "url", "affiliate_url", "api_key", "mpn", "mpn_found"}

    for row in result["parts_list"]:
        assert forbidden.isdisjoint(row)


def test_gateway_procurement_endpoint_is_separate_from_generation_contract():
    result = build_done_result(HARDCODED_CIRCUIT)

    status, response = build_procurement_gateway_http_response(
        {"parts_list": result["parts_list"], "supplier": "jameco", "quantity": 1},
        config=AvantLinkConfig(enabled=False, jameco_approved=False, affiliate_id="", website_id=""),
    )

    assert status == 200
    assert response["procurement_status"] == "credentials_required"
    assert response["cart_actions"] == []
    assert response["link_actions"] == []
    assert "parts_list" in result
    assert "supplier_matches" not in result
    assert "link_actions" not in result


def test_gateway_jameco_preflight_is_separate_from_parts_generation_and_redacts_credentials():
    status, response = build_jameco_preflight_gateway_http_response(
        config=AvantLinkConfig(
            enabled=True,
            jameco_approved=True,
            affiliate_id="secret-affiliate-id",
            website_id="secret-website-id",
        )
    )

    assert status == 200
    assert response["supplier"] == "jameco"
    assert response["network"] == "avantlink"
    assert response["preflight_status"] == "ready_for_live_lookup"
    assert response["ready_for_live_lookup"] is True
    assert "secret-affiliate-id" not in str(response)
    assert "parts_list" not in response
