"""Link-out procurement: zero-credential search links, env-gated affiliate wrap."""

import os
from unittest.mock import patch

from shared.procurement import build_procurement_response

ROWS = [
    {"id": "C1", "is_part": True, "parts_list_part": "capacitor ceramic",
     "value": "100nF", "package": "0603"},
    {"id": "GND1", "is_part": False, "parts_list_part": "power symbol"},
]

RESISTOR_ROWS = [
    {"id": "R1", "is_part": True, "parts_list_part": "resistor",
     "value": "330Ω", "package": "1/4W"},
]


def test_digikey_plain_linkout_needs_no_credentials():
    r = build_procurement_response(ROWS, supplier="digikey")
    assert r["procurement_status"] == "links_ready"
    [a] = r["link_actions"]
    assert a["type"] == "open_search_link"
    assert a["url"].startswith("https://www.digikey.com/en/products?keywords=")
    assert "100nF" in a["url"] and "0603" in a["url"]
    assert "disclosure" not in a                      # nothing to disclose: no referral
    assert r["eligibility_disclosures"] == []


def test_affiliate_wrap_adds_tracking_and_disclosure():
    with patch.dict(os.environ, {"OHMATIC_LINKOUT_WRAP_DIGIKEY":
                                 "https://track.example/c/123?u={url}"}):
        r = build_procurement_response(ROWS, supplier="digikey")
    [a] = r["link_actions"]
    assert a["type"] == "open_referral_product_link"
    assert a["url"].startswith("https://track.example/c/123?u=")
    assert "disclosure" in a and "commission" in a["disclosure"]
    assert r["eligibility_disclosures"]


def test_ohm_symbol_is_spelled_out_so_digikey_returns_results():
    # The Ω glyph URL-encodes to %CE%A9, which DigiKey keyword search can't match
    # (empty results). The query must spell it "ohm" -> "330ohm".
    [a] = build_procurement_response(RESISTOR_ROWS, supplier="digikey")["link_actions"]
    assert "330ohm" in a["url"]
    assert "%CE%A9" not in a["url"] and "Ω" not in a["url"]


def test_newark_and_lcsc_patterns():
    assert "newark.com/search?st=" in build_procurement_response(
        ROWS, supplier="newark")["link_actions"][0]["url"]
    assert "lcsc.com/search?q=" in build_procurement_response(
        ROWS, supplier="lcsc")["link_actions"][0]["url"]


def test_jameco_path_unchanged_and_unknown_still_rejected():
    assert build_procurement_response(ROWS, supplier="jameco")[
        "procurement_status"] == "credentials_required"
    assert build_procurement_response(ROWS, supplier="nope")[
        "procurement_status"] == "unsupported_supplier"
