from shared.procurement import (
    AvantLinkConfig,
    build_jameco_preflight_response,
    build_procurement_http_response,
    build_procurement_response,
)


def _parts_list():
    return [
        {
            "id": "R1",
            "type": "resistor",
            "parts_list_part": "resistor",
            "value": "10k",
            "package": "0603",
            "description": "resistor 10k 0603",
            "is_part": True,
            "match_status": "local_only",
        },
        {
            "id": "VCC1",
            "type": "power_vcc",
            "parts_list_part": "power_vcc",
            "value": "5V",
            "package": "VCC",
            "description": "power_vcc 5V VCC",
            "is_part": False,
            "match_status": "local_only",
        },
    ]


def test_jameco_procurement_is_disabled_without_affiliate_credentials():
    calls = []

    def fake_fetch(_url):
        calls.append(_url)
        return []

    response = build_procurement_response(
        _parts_list(),
        quantity=2,
        supplier="jameco",
        config=AvantLinkConfig(enabled=False, jameco_approved=False, affiliate_id="", website_id=""),
        fetch_json=fake_fetch,
    )

    assert response["procurement_status"] == "credentials_required"
    assert response["supplier_matches"] == []
    assert response["link_actions"] == []
    assert response["cart_actions"] == []
    assert response["eligibility_disclosures"] == []
    assert calls == []


def test_jameco_procurement_uses_avantlink_search_and_returns_tracked_links():
    seen_urls = []

    def fake_fetch(url):
        seen_urls.append(url)
        return [
            {
                "Merchant Name": "Jameco Electronics",
                "Product SKU": "691104",
                "Product Name": "10K Ohm Resistor",
                "Brand Name": "Jameco ValuePro",
                "Retail Price": "0.05",
                "Buy URL": "https://classic.avantlink.com/click.php?tracked=R1",
                "Match Score": "98",
            }
        ]

    response = build_procurement_response(
        _parts_list(),
        quantity=3,
        supplier="jameco",
        config=AvantLinkConfig(
            enabled=True,
            jameco_approved=True,
            affiliate_id="123",
            website_id="456",
            merchant_id="789",
            custom_tracking_prefix="ohmatic",
        ),
        fetch_json=fake_fetch,
    )

    assert response["procurement_status"] == "matches_ready"
    assert len(response["supplier_matches"]) == 1
    match = response["supplier_matches"][0]
    assert match["part_id"] == "R1"
    assert match["supplier"] == "jameco"
    assert match["availability"] == "unknown"
    assert match["matched_product"]["sku"] == "691104"
    assert match["matched_product"]["name"] == "10K Ohm Resistor"
    assert match["matched_product"]["referral_url"] == "https://classic.avantlink.com/click.php?tracked=R1"
    assert response["link_actions"] == [
        {
            "type": "open_referral_product_link",
            "part_id": "R1",
            "supplier": "jameco",
            "quantity": 3,
            "url": "https://classic.avantlink.com/click.php?tracked=R1",
            "label": "Open Jameco product link for R1",
            "disclosure": "Ohmatic may earn a commission from qualifying purchases through this Jameco link.",
        }
    ]
    assert response["cart_actions"] == []
    assert response["eligibility_disclosures"] == [
        "Ohmatic may earn a commission from qualifying purchases through this Jameco link."
    ]
    assert len(seen_urls) == 1
    assert "module=ProductSearch" in seen_urls[0]
    assert "affiliate_id=123" in seen_urls[0]
    assert "website_id=456" in seen_urls[0]
    assert "merchant_ids=789" in seen_urls[0]
    assert "custom_tracking_code=ohmatic-R1" in seen_urls[0]
    assert "search_term=resistor+10k+0603" in seen_urls[0]


def test_jameco_procurement_returns_explicit_feed_miss_without_scraping():
    response = build_procurement_response(
        _parts_list(),
        quantity=1,
        supplier="jameco",
        config=AvantLinkConfig(enabled=True, jameco_approved=True, affiliate_id="123", website_id="456"),
        fetch_json=lambda _url: [],
    )

    assert response["procurement_status"] == "no_matches"
    assert response["supplier_matches"] == [
        {
            "part_id": "R1",
            "supplier": "jameco",
            "query": "resistor 10k 0603",
            "match_status": "not_available_from_permitted_feed",
            "availability": "unknown",
            "warnings": ["No Jameco match returned by the permitted AvantLink feed/API."],
        }
    ]
    assert response["link_actions"] == []
    assert response["cart_actions"] == []


def test_procurement_http_contract_rejects_missing_parts_list():
    status, response = build_procurement_http_response({})

    assert status == 400
    assert response == {"error": "missing 'parts_list' field"}


def test_jameco_preflight_reports_missing_approval_and_credentials_without_network_or_secrets():
    response = build_jameco_preflight_response(
        config=AvantLinkConfig(enabled=False, jameco_approved=False, affiliate_id="", website_id="")
    )

    assert response["preflight_status"] == "needs_setup"
    assert response["ready_for_live_lookup"] is False
    required_by_id = {item["id"]: item for item in response["required"]}
    assert required_by_id["OHMATIC_JAMECO_APPROVED"]["done"] is False
    assert required_by_id["OHMATIC_JAMECO_ENABLED"]["done"] is False
    assert required_by_id["AVANTLINK_AFFILIATE_ID"]["done"] is False
    assert required_by_id["AVANTLINK_WEBSITE_ID"]["done"] is False
    assert response["blocked_until_ready"] == [
        "live Jameco ProductSearch calls",
        "Jameco referral product links",
        "Jameco price or product data display",
    ]
    assert "cart filling" in response["never_allowed"]
    assert "storefront scraping" in response["never_allowed"]
    serialized = str(response)
    assert "123" not in serialized
    assert "456" not in serialized


def test_jameco_preflight_ready_state_is_redacted_and_requires_explicit_program_approval():
    response = build_jameco_preflight_response(
        config=AvantLinkConfig(
            enabled=True,
            jameco_approved=True,
            affiliate_id="secret-affiliate-id",
            website_id="secret-website-id",
            merchant_id="secret-merchant-id",
            datafeed_id="secret-datafeed-id",
            app_id="secret-app-id",
        )
    )

    assert response["preflight_status"] == "ready_for_live_lookup"
    assert response["ready_for_live_lookup"] is True
    assert all(item["done"] for item in response["required"])
    assert response["optional"][0] == {
        "id": "AVANTLINK_JAMECO_MERCHANT_ID",
        "label": "Jameco merchant filter for narrower AvantLink ProductSearch results",
        "done": True,
        "required": False,
    }
    serialized = str(response)
    assert "secret-affiliate-id" not in serialized
    assert "secret-website-id" not in serialized
    assert "secret-merchant-id" not in serialized
