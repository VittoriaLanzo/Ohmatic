from pathlib import Path

from shared.parts_list import build_parts_list


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "verifier/config/component_registry.toml"


def _sample_circuit():
    return {
        "metadata": {
            "title": "Parts List Test",
            "description": "Circuit with physical and schematic-only components.",
            "version": "0.1",
            "tags": ["parts"],
        },
        "components": [
            {
                "id": "VCC1",
                "type": "power_vcc",
                "part": "VCC",
                "value": "5V",
                "pins": {"1": "VCC"},
                "x": 0,
                "y": 0,
            },
            {
                "id": "R1",
                "type": "resistor",
                "part": "0603",
                "value": "10k",
                "pins": {"1": "VCC", "2": "OUT"},
                "x": 10,
                "y": 0,
            },
            {
                "id": "U1",
                "type": "ic_timer",
                "part": "NE555",
                "value": "",
                "pins": {"VCC": "VCC", "GND": "GND", "OUT": "OUT"},
                "x": 20,
                "y": 0,
            },
            {
                "id": "GND1",
                "type": "power_gnd",
                "part": "GND",
                "value": "",
                "pins": {"1": "GND"},
                "x": 30,
                "y": 0,
            },
        ],
        "nets": [
            {"name": "VCC", "pins": ["VCC1.1", "R1.1", "U1.VCC"]},
            {"name": "OUT", "pins": ["R1.2", "U1.OUT"]},
            {"name": "GND", "pins": ["U1.GND", "GND1.1"]},
        ],
    }


def test_parts_list_is_deterministic_and_preserves_component_order():
    first = build_parts_list(_sample_circuit(), registry_path=REGISTRY)
    second = build_parts_list(_sample_circuit(), registry_path=REGISTRY)

    assert first == second
    assert [row["id"] for row in first] == ["VCC1", "R1", "U1", "GND1"]


def test_parts_list_marks_non_physical_symbols_not_buyable():
    rows = build_parts_list(_sample_circuit(), registry_path=REGISTRY)

    by_id = {row["id"]: row for row in rows}
    assert by_id["VCC1"]["is_physical"] is False
    assert by_id["VCC1"]["buyable"] is False
    assert by_id["GND1"]["is_physical"] is False
    assert by_id["GND1"]["buyable"] is False
    assert by_id["R1"]["is_physical"] is True
    assert by_id["R1"]["buyable"] is True


def test_parts_list_uses_registry_parts_metadata_without_supplier_fields():
    rows = build_parts_list(_sample_circuit(), registry_path=REGISTRY)

    resistor = next(row for row in rows if row["id"] == "R1")
    assert resistor == {
        "id": "R1",
        "type": "resistor",
        "parts_list_part": "resistor",
        "value": "10k",
        "package": "0603",
        "description": "resistor 10k 0603",
        "is_physical": True,
        "buyable": True,
        "match_status": "local_only",
    }
    forbidden = {"supplier", "price_usd", "stock", "url", "affiliate_url", "api_key", "mpn"}
    assert forbidden.isdisjoint(resistor)

