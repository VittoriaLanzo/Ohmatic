"""Post-parts-list procurement helpers.

This module is intentionally separate from Step 2 generation. It may return
supplier/referral data only from approved procurement endpoints and must not be
used to add supplier fields to circuit JSON or deterministic parts_list rows.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote_plus, urlencode
from urllib.request import urlopen


JAMECO_DISCLOSURE = "Ohmatic may earn a commission from qualifying purchases through this Jameco link."
AVANTLINK_PRODUCT_SEARCH_URL = "https://classic.avantlink.com/api.php"


@dataclass(frozen=True)
class AvantLinkConfig:
    enabled: bool
    jameco_approved: bool
    affiliate_id: str
    website_id: str
    merchant_id: str = ""
    datafeed_id: str = ""
    app_id: str = ""
    custom_tracking_prefix: str = "ohmatic"
    base_url: str = AVANTLINK_PRODUCT_SEARCH_URL
    timeout_seconds: float = 8.0

    @classmethod
    def from_env(cls) -> "AvantLinkConfig":
        return cls(
            enabled=os.environ.get("OHMATIC_JAMECO_ENABLED") == "1",
            jameco_approved=os.environ.get("OHMATIC_JAMECO_APPROVED") == "1",
            affiliate_id=os.environ.get("AVANTLINK_AFFILIATE_ID", ""),
            website_id=os.environ.get("AVANTLINK_WEBSITE_ID", ""),
            merchant_id=os.environ.get("AVANTLINK_JAMECO_MERCHANT_ID", ""),
            datafeed_id=os.environ.get("AVANTLINK_JAMECO_DATAFEED_ID", ""),
            app_id=os.environ.get("AVANTLINK_APP_ID", ""),
            custom_tracking_prefix=os.environ.get("OHMATIC_AFFILIATE_TRACKING_PREFIX", "ohmatic"),
        )

    def is_ready(self) -> bool:
        return self.enabled and self.jameco_approved and bool(self.affiliate_id) and bool(self.website_id)


FetchJson = Callable[[str], Any]


def build_jameco_preflight_response(*, config: AvantLinkConfig | None = None) -> dict[str, Any]:
    config = config or AvantLinkConfig.from_env()
    required = [
        _preflight_item(
            "OHMATIC_JAMECO_APPROVED",
            "Jameco affiliate program approval has been confirmed outside the repo",
            config.jameco_approved,
            required=True,
        ),
        _preflight_item(
            "OHMATIC_JAMECO_ENABLED",
            "Live Jameco lookup is explicitly enabled for this runtime",
            config.enabled,
            required=True,
        ),
        _preflight_item(
            "AVANTLINK_AFFILIATE_ID",
            "Approved AvantLink affiliate identifier is configured",
            bool(config.affiliate_id),
            required=True,
        ),
        _preflight_item(
            "AVANTLINK_WEBSITE_ID",
            "Approved AvantLink website identifier is configured",
            bool(config.website_id),
            required=True,
        ),
    ]
    optional = [
        _preflight_item(
            "AVANTLINK_JAMECO_MERCHANT_ID",
            "Jameco merchant filter for narrower AvantLink ProductSearch results",
            bool(config.merchant_id),
            required=False,
        ),
        _preflight_item(
            "AVANTLINK_JAMECO_DATAFEED_ID",
            "Jameco datafeed filter when AvantLink exposes one for the approved relationship",
            bool(config.datafeed_id),
            required=False,
        ),
        _preflight_item(
            "AVANTLINK_APP_ID",
            "Optional AvantLink app identifier for app-specific tracking",
            bool(config.app_id),
            required=False,
        ),
    ]
    ready = all(item["done"] for item in required)
    return {
        "supplier": "jameco",
        "network": "avantlink",
        "preflight_status": "ready_for_live_lookup" if ready else "needs_setup",
        "ready_for_live_lookup": ready,
        "required": required,
        "optional": optional,
        "allowed_before_ready": [
            "local deterministic parts_list generation",
            "Jameco setup guidance",
            "non-network procurement preflight checks",
        ],
        "blocked_until_ready": [
            "live Jameco ProductSearch calls",
            "Jameco referral product links",
            "Jameco price or product data display",
        ],
        "never_allowed": [
            "cart filling",
            "storefront scraping",
            "undisclosed affiliate links",
        ],
        "disclosure": JAMECO_DISCLOSURE,
    }




# ── Zero-credential link-out suppliers ─────────────────────────────────────────
# Search deep-links that need NO credentials or approval (research 2026-06: the
# param names are the load-bearing detail). Affiliate tracking is optional and
# env-gated: set OHMATIC_LINKOUT_WRAP_<SUPPLIER> to a template containing {url}
# (e.g. an Impact/CJ deep-link wrapper) once the program approves you - links
# then carry the disclosure. Without it, plain disclosed-free search links.
#
# TODO(vittoria): after affiliate approvals, set in .env (NEVER commit values):
#   OHMATIC_LINKOUT_WRAP_DIGIKEY  - Impact (impact.com) deep-link template, {url} placeholder
#   OHMATIC_LINKOUT_WRAP_NEWARK   - CJ Affiliate deep-link template, {url} placeholder
#   (LCSC has no self-serve affiliate program - links stay plain)
# Verified 2026-06-12: newark/lcsc search URLs fetch HTTP 200 with result pages;
# digikey 403s PROGRAMMATIC fetches (Akamai bot wall) but opens fine in a real
# browser - which is the only way these links are ever used (link-OUT).
#
# PRICE DISPLAY (phase 2) - ToS rule: NEVER scrape storefront HTML for prices.
# Prices come ONLY from the official APIs (free tiers, self-serve signup):
#   DigiKey Product Information V4 (developer.digikey.com, 1k searches/day)
#     -> env DIGIKEY_CLIENT_ID / DIGIKEY_CLIENT_SECRET
#   element14 Partner API (partner.element14.com, real-time price+stock)
#     -> env ELEMENT14_API_KEY
# API ToS also restrict CACHING: fetch prices live (or cache minutes, not days)
# and attribute the source. This module stays scrape-free by design.
LINKOUT_SUPPLIERS: dict[str, dict[str, str]] = {
    "digikey": {
        "search": "https://www.digikey.com/en/products?keywords={query}",
        "label": "DigiKey",
        "disclosure": "Ohmatic may earn a commission from qualifying purchases through this DigiKey link.",
    },
    "newark": {
        "search": "https://www.newark.com/search?st={query}",
        "label": "Newark / element14",
        "disclosure": "Ohmatic may earn a commission from qualifying purchases through this Newark link.",
    },
    "lcsc": {
        "search": "https://www.lcsc.com/search?q={query}",
        "label": "LCSC",
        "disclosure": "Ohmatic may earn a commission from qualifying purchases through this LCSC link.",
    },
}


def _linkout_wrap_template(supplier: str) -> str:
    return os.environ.get(f"OHMATIC_LINKOUT_WRAP_{supplier.upper()}", "").strip()


def build_linkout_response(
    parts_list: list[dict[str, Any]],
    *,
    supplier: str,
    quantity: int = 1,
) -> dict[str, Any]:
    """Search-link procurement for LINKOUT_SUPPLIERS - no API, no credentials.

    Each buyable parts_list row becomes one search deep-link. When the
    supplier's affiliate wrap template is configured (program approved), the
    link is wrapped and carries the disclosure; otherwise it is a plain link.
    """
    info = LINKOUT_SUPPLIERS[supplier]
    wrap = _linkout_wrap_template(supplier)
    link_actions: list[dict[str, Any]] = []
    for row in parts_list:
        if not row.get("buyable"):
            continue
        part_id = _string(row.get("id"))
        query = _query_for_parts_row(row)
        if not query:
            continue
        url = info["search"].format(query=quote_plus(query))
        action = {
            "type": "open_search_link",
            "part_id": part_id,
            "supplier": supplier,
            "quantity": quantity,
            "url": url,
            "label": f"Search {info['label']} for {part_id}",
        }
        if wrap:
            action["type"] = "open_referral_product_link"
            action["url"] = wrap.format(url=quote_plus(url))
            action["disclosure"] = info["disclosure"]
        link_actions.append(action)
    return {
        "procurement_status": "links_ready" if link_actions else "no_matches",
        "supplier_matches": [],
        "link_actions": link_actions,
        "cart_actions": [],
        "eligibility_disclosures": [info["disclosure"]] if (wrap and link_actions) else [],
        "supplier": supplier,
    }


def build_procurement_response(
    parts_list: list[dict[str, Any]],
    *,
    quantity: int = 1,
    supplier: str = "jameco",
    region: str | None = None,
    currency: str | None = None,
    config: AvantLinkConfig | None = None,
    fetch_json: FetchJson | None = None,
) -> dict[str, Any]:
    if supplier in LINKOUT_SUPPLIERS:
        return build_linkout_response(parts_list, supplier=supplier, quantity=quantity)
    if supplier != "jameco":
        return {
            "procurement_status": "unsupported_supplier",
            "supplier_matches": [],
            "link_actions": [],
            "cart_actions": [],
            "eligibility_disclosures": [],
            "warnings": [f"unsupported procurement supplier: {supplier}"],
        }

    config = config or AvantLinkConfig.from_env()
    if not config.is_ready():
        return {
            "procurement_status": "credentials_required",
            "supplier_matches": [],
            "link_actions": [],
            "cart_actions": [],
            "eligibility_disclosures": [],
            "warnings": [
                "Jameco procurement requires confirmed Jameco affiliate approval plus approved AvantLink affiliate_id and website_id."
            ],
        }

    fetch_json = fetch_json or _fetch_json
    quantity = max(1, int(quantity))
    supplier_matches: list[dict[str, Any]] = []
    link_actions: list[dict[str, Any]] = []

    for row in parts_list:
        if not row.get("buyable"):
            continue
        part_id = _string(row.get("id"))
        query = _query_for_parts_row(row)
        records = _records_from_response(fetch_json(_avantlink_product_search_url(config, query, part_id)))
        if not records:
            supplier_matches.append(_miss(part_id, query))
            continue
        match = _match_from_record(part_id, query, records[0])
        supplier_matches.append(match)
        referral_url = match["matched_product"].get("referral_url", "")
        if referral_url:
            link_actions.append(
                {
                    "type": "open_referral_product_link",
                    "part_id": part_id,
                    "supplier": "jameco",
                    "quantity": quantity,
                    "url": referral_url,
                    "label": f"Open Jameco product link for {part_id}",
                    "disclosure": JAMECO_DISCLOSURE,
                }
            )

    status = "matches_ready" if link_actions else "no_matches"
    return {
        "procurement_status": status,
        "supplier_matches": supplier_matches,
        "link_actions": link_actions,
        "cart_actions": [],
        "eligibility_disclosures": [JAMECO_DISCLOSURE] if link_actions else [],
        "supplier": "jameco",
        "region": region,
        "currency": currency,
    }


def build_procurement_http_response(
    payload: dict[str, Any],
    *,
    config: AvantLinkConfig | None = None,
    fetch_json: FetchJson | None = None,
) -> tuple[int, dict[str, Any]]:
    if not isinstance(payload, dict):
        return 400, {"error": "request body must be a JSON object"}
    if "parts_list" not in payload:
        return 400, {"error": "missing 'parts_list' field"}
    parts_list = payload["parts_list"]
    if not isinstance(parts_list, list):
        return 400, {"error": "'parts_list' must be a list"}
    supplier = payload.get("supplier", "jameco")
    if not isinstance(supplier, str):
        return 400, {"error": "'supplier' must be a string"}
    quantity = payload.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        return 400, {"error": "'quantity' must be a positive integer"}
    try:
        response = build_procurement_response(
            parts_list,
            quantity=quantity,
            supplier=supplier,
            region=_optional_string(payload.get("region")),
            currency=_optional_string(payload.get("currency")),
            config=config,
            fetch_json=fetch_json,
        )
    except Exception as exc:
        return 502, {"error": "procurement_lookup_failed", "message": str(exc)}
    return 200, response


def _fetch_json(url: str) -> Any:
    with urlopen(url, timeout=AvantLinkConfig.from_env().timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _preflight_item(id: str, label: str, done: bool, *, required: bool) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "done": done,
        "required": required,
    }


def _avantlink_product_search_url(config: AvantLinkConfig, query: str, part_id: str) -> str:
    params = {
        "module": "ProductSearch",
        "affiliate_id": config.affiliate_id,
        "website_id": config.website_id,
        "search_term": query,
        "output": "json",
        "search_results_count": "1",
        "search_results_fields": (
            "Merchant Name|Product SKU|Product Name|Brand Name|Retail Price|"
            "Sale Price|Buy URL|Product URL|Match Score"
        ),
    }
    if config.merchant_id:
        params["merchant_ids"] = config.merchant_id
    if config.datafeed_id:
        params["datafeed_ids"] = config.datafeed_id
    if config.app_id:
        params["app_id"] = config.app_id
    if config.custom_tracking_prefix:
        params["custom_tracking_code"] = f"{config.custom_tracking_prefix}-{part_id}"
    return f"{config.base_url}?{urlencode(params)}"


def _query_for_parts_row(row: dict[str, Any]) -> str:
    parts = [
        _string(row.get("parts_list_part")),
        _string(row.get("value")),
        _string(row.get("package")),
    ]
    return " ".join(part for part in parts if part)


def _records_from_response(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [record for record in response if isinstance(record, dict)]
    if not isinstance(response, dict):
        return []
    for key in ("products", "Products", "items", "Items", "results", "Results"):
        value = response.get(key)
        if isinstance(value, list):
            return [record for record in value if isinstance(record, dict)]
    for value in response.values():
        if isinstance(value, list):
            return [record for record in value if isinstance(record, dict)]
    return [response]


def _match_from_record(part_id: str, query: str, record: dict[str, Any]) -> dict[str, Any]:
    score = _float_or_none(_get(record, "Match Score", "match_score", "matchScore"))
    return {
        "part_id": part_id,
        "supplier": "jameco",
        "query": query,
        "match_status": "matched",
        "availability": _availability(record),
        "confidence": round(score / 100, 4) if score is not None and score > 1 else score,
        "matched_product": {
            "sku": _get(record, "Product SKU", "sku", "productSku"),
            "name": _get(record, "Product Name", "name", "productName"),
            "brand": _get(record, "Brand Name", "brand", "brandName"),
            "price": _get(record, "Sale Price", "Retail Price", "price"),
            "referral_url": _get(record, "Buy URL", "buy_url", "buyUrl"),
            "product_url": _get(record, "Product URL", "product_url", "productUrl"),
        },
        "warnings": ["Availability is unknown unless the permitted feed/API returns an explicit stock field."],
    }


def _miss(part_id: str, query: str) -> dict[str, Any]:
    return {
        "part_id": part_id,
        "supplier": "jameco",
        "query": query,
        "match_status": "not_available_from_permitted_feed",
        "availability": "unknown",
        "warnings": ["No Jameco match returned by the permitted AvantLink feed/API."],
    }


def _availability(record: dict[str, Any]) -> str:
    value = _get(record, "Availability", "availability", "Stock Status", "stock_status", "stockStatus")
    return value or "unknown"


def _get(record: dict[str, Any], *names: str) -> str:
    lowered = {key.lower().replace("_", " "): value for key, value in record.items()}
    for name in names:
        value = record.get(name)
        if value is not None:
            return _string(value)
        value = lowered.get(name.lower().replace("_", " "))
        if value is not None:
            return _string(value)
    return ""


def _float_or_none(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return _string(value)


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
