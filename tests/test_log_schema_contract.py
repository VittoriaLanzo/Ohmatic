from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_log_schema_documents_local_parts_list_not_supplier_metrics():
    text = (ROOT / "shared/docs/log_schema.md").read_text(encoding="utf-8")
    # Enrichment is gateway-internal: the parts-list log fields live under the gateway.
    gateway_section = text.split("### gateway", 1)[1].split("### inference", 1)[0]

    assert "`parts_list_entries`" in gateway_section
    assert "`buyable_parts`" in gateway_section
    assert "`non_physical_symbols`" in gateway_section
    assert "`supplier`" not in text
    assert "`bom_entries`" not in text
    assert "`mpn_hit_rate`" not in text
