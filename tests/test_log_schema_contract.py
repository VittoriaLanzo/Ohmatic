from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_enricher_log_schema_documents_local_parts_list_not_supplier_metrics():
    text = (ROOT / "shared/docs/log_schema.md").read_text(encoding="utf-8")
    enricher_section = text.split("### enricher", 1)[1].split("## Example Log Lines", 1)[0]

    assert "`parts_list_entries`" in enricher_section
    assert "`buyable_parts`" in enricher_section
    assert "`non_physical_symbols`" in enricher_section
    assert "`supplier`" not in enricher_section
    assert "`bom_entries`" not in enricher_section
    assert "`mpn_hit_rate`" not in enricher_section
