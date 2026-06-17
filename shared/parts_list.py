"""Deterministic local parts-list generation for verified Ohmatic circuits."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import tomllib


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "verifier/config/component_registry.toml"


def build_parts_list(
    circuit: dict[str, Any],
    *,
    registry_path: Path | str = DEFAULT_REGISTRY_PATH,
) -> list[dict[str, Any]]:
    """Return deterministic local parts rows in circuit component order."""
    registry = _load_parts_registry(Path(registry_path))
    rows: list[dict[str, Any]] = []

    components = circuit.get("components", [])
    if not isinstance(components, list):
        return rows

    for component in components:
        if not isinstance(component, dict):
            continue
        component_type = component.get("type")
        metadata = registry.get(component_type)
        if metadata is None:
            raise ValueError(f"unknown component type for parts_list: {component_type!r}")

        value = _string_field(component, "value")
        package = _string_field(component, "part")
        is_physical = bool(metadata["is_physical"])
        row = {
            "id": _string_field(component, "id"),
            "type": component_type,
            "parts_list_part": metadata["parts_list_part"],
            "value": value,
            "package": package,
            "description": _description(metadata["parts_list_part"], value, package),
            "is_part": is_physical,
            "match_status": "local_only",
        }
        rows.append(row)

    return rows


def _load_parts_registry(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("rb") as f:
        raw = tomllib.load(f)

    registry: dict[str, dict[str, Any]] = {}
    for component_type, metadata in raw.items():
        if component_type == "defaults":
            continue
        if not isinstance(metadata, dict):
            continue
        parts_list_part = metadata.get("parts_list_part")
        is_physical = metadata.get("is_physical")
        if not isinstance(parts_list_part, str) or not isinstance(is_physical, bool):
            raise ValueError(f"registry entry {component_type!r} is missing parts_list metadata")
        registry[component_type] = {
            "parts_list_part": parts_list_part,
            "is_physical": is_physical,
        }
    return registry


def _string_field(component: dict[str, Any], field: str) -> str:
    value = component.get(field)
    return value if isinstance(value, str) else ""


def _description(parts_list_part: str, value: str, package: str) -> str:
    return " ".join(part for part in (parts_list_part, value, package) if part)

