#!/usr/bin/env python3
"""
Validate circuit schematics against schema v0.1.
"""
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "verifier/config/component_registry.toml"
FORBIDDEN_FIELDS = {
    "bom",
    "supplier",
    "price_usd",
    "stock",
    "url",
    "affiliate",
    "mpn",
    "manufacturer",
    "octopart",
    "poll_url",
}
FORBIDDEN_FIELD_STEMS = {
    "affiliate",
    "api",
    "bom",
    "key",
    "manufacturer",
    "mpn",
    "octopart",
    "price",
    "secret",
    "stock",
    "supplier",
    "token",
    "url",
}
PIN_REF_RE = re.compile(r'^[A-Z][A-Za-z0-9_]*\.[A-Za-z0-9_+\-]+$')
ALLOWED_COMPONENT_FIELDS_FLAT   = {"id", "type", "value", "part", "x", "y", "pins"}  # old format
ALLOWED_COMPONENT_FIELDS_TOPO   = {"id", "type", "value", "part", "pins"}              # STAGE_1_TOPOLOGY
ALLOWED_SPATIAL_NODE_FIELDS     = {"id", "x", "y"}                                     # STAGE_2_LAYOUT
ALLOWED_NET_FIELDS = {"name", "pins"}


# ── Format resolver ───────────────────────────────────────────────────────────

def resolve_circuit_topology(circuit: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize old flat format and new STAGE_1/STAGE_2 format into a common dict.

    Returns a dict with keys: ``metadata``, ``components``, ``nets``,
    ``spatial_nodes``, and ``_is_v2`` (bool).  Callers use this dict instead
    of accessing circuit keys directly so both formats are handled identically.
    """
    if "STAGE_1_TOPOLOGY" in circuit:
        topo   = circuit.get("STAGE_1_TOPOLOGY") or {}
        layout = circuit.get("STAGE_2_LAYOUT")   or {}
        return {
            "metadata":      circuit.get("metadata", {}),
            "components":    topo.get("components", []),
            "nets":          topo.get("nets", []),
            "spatial_nodes": layout.get("spatial_nodes", []),
            "_is_v2":        True,
        }
    return {
        "metadata":      circuit.get("metadata", {}),
        "components":    circuit.get("components", []),
        "nets":          circuit.get("nets", []),
        "spatial_nodes": [],
        "_is_v2":        False,
    }
MAX_COMPONENTS = 10_000
MAX_NETS = 10_000


def load_registry_component_types(path: Path) -> Set[str]:
    """Load component type names from the TOML registry."""
    with open(path, "rb") as f:
        registry = tomllib.load(f)
    return {key for key in registry if key != "defaults"}


def load_schema_component_types(path: Path) -> Set[str]:
    """Load component type enum values from the JSON schema."""
    with open(path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    component_type = schema["properties"]["components"]["items"]["properties"]["type"]
    return set(component_type["enum"])


def check_registry_schema_drift(registry_path: Path, schema_path: Path) -> List[str]:
    """Return registry/schema component type mismatches."""
    registry = load_registry_component_types(registry_path)
    schema = load_schema_component_types(schema_path)
    errors: List[str] = []
    missing_from_schema = sorted(registry - schema)
    missing_from_registry = sorted(schema - registry)
    if missing_from_schema:
        errors.append(f"registry types missing from schema enum: {missing_from_schema}")
    if missing_from_registry:
        errors.append(f"schema enum types missing from registry: {missing_from_registry}")
    return errors


def check_registry_parts_metadata(path: Path) -> List[str]:
    """Check local parts_list metadata exists and contains no supplier-style fields."""
    with open(path, "rb") as f:
        registry = tomllib.load(f)

    errors: List[str] = []
    for component_type, metadata in registry.items():
        if component_type == "defaults":
            continue
        if not isinstance(metadata.get("parts_list_part"), str) or not metadata.get("parts_list_part"):
            errors.append(f"{component_type} missing parts_list_part")
        if not isinstance(metadata.get("is_physical"), bool):
            errors.append(f"{component_type} missing boolean is_physical")

        forbidden = sorted(key for key in metadata if is_forbidden_field(key))
        if forbidden:
            errors.append(f"{component_type} has forbidden fields: {forbidden}")

    return errors


def is_forbidden_field(key: str) -> bool:
    """Return True for supplier/BOM-style field names, including derived forms."""
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if normalized in FORBIDDEN_FIELDS:
        return True
    tokens = {token for token in normalized.split("_") if token}
    if tokens & FORBIDDEN_FIELD_STEMS:
        return True
    return any(stem in normalized for stem in {"octopart"})


class SchemaValidator:
    """Validates circuit JSON against schema v0.1."""

    def __init__(
        self,
        valid_component_types: Set[str] | None = None,
        registry_path: Path | None = None,
    ) -> None:
        self.errors: List[str] = []
        self.valid_component_types = (
            valid_component_types
            if valid_component_types is not None
            else load_registry_component_types(registry_path or DEFAULT_REGISTRY_PATH)
        )

    def validate_circuit(self, circuit: Dict[str, Any]) -> bool:
        """Validate a complete circuit. Returns True if valid.

        Accepts both the old flat format (``components``/``nets`` at circuit
        root) and the new two-stage format (``STAGE_1_TOPOLOGY`` /
        ``STAGE_2_LAYOUT``).  All sections are always checked so the caller
        receives the full error set in a single pass.
        """
        self.errors.clear()

        if not isinstance(circuit, dict):
            self.errors.append(f"circuit must be a JSON object, got {type(circuit).__name__}")
            return False

        self._validate_forbidden_fields(circuit)

        resolved = resolve_circuit_topology(circuit)
        is_v2    = resolved["_is_v2"]

        # --- metadata ---
        if "metadata" not in circuit:
            self.errors.append("Missing 'metadata' field")
        else:
            self._validate_metadata(circuit["metadata"])

        # --- structural key check (format-aware) ---
        if is_v2:
            if not isinstance(circuit.get("STAGE_1_TOPOLOGY"), dict):
                self.errors.append("STAGE_1_TOPOLOGY must be a JSON object")
            if not isinstance(circuit.get("STAGE_2_LAYOUT"), dict):
                self.errors.append("STAGE_2_LAYOUT must be a JSON object")
        else:
            if "components" not in circuit:
                self.errors.append("Missing 'components' field")
            if "nets" not in circuit:
                self.errors.append("Missing 'nets' field")

        # --- components ---
        components: List[Dict[str, Any]] = []
        raw_components = resolved["components"]
        if not isinstance(raw_components, list) or len(raw_components) == 0:
            self.errors.append("'components' must be a non-empty list")
            if not isinstance(raw_components, list):
                self.errors.append("Missing required power_vcc component")
                self.errors.append("Missing required power_gnd component")
        else:
            components = raw_components
            self._validate_components(components, is_v2=is_v2)

        # --- nets ---
        raw_nets = resolved["nets"]
        if not isinstance(raw_nets, list) or len(raw_nets) == 0:
            self.errors.append("'nets' must be a non-empty list")
        else:
            self._validate_nets(raw_nets, components)

        # --- spatial layout (v2 only) ---
        if is_v2:
            self._validate_spatial_layout(resolved["spatial_nodes"], components)

        return len(self.errors) == 0

    def _validate_metadata(self, metadata: Dict[str, Any]) -> None:
        """Validate metadata section."""
        if not isinstance(metadata, dict):
            self.errors.append(f"'metadata' must be a JSON object, got {type(metadata).__name__}")
            return
        required = {"title", "description", "version", "tags"}
        missing = required - set(metadata.keys())
        if missing:
            self.errors.append(f"metadata missing required fields: {sorted(missing)}")

        if "title" in metadata:
            title = metadata["title"]
            if not isinstance(title, str):
                self.errors.append("metadata.title must be a string")
            elif len(title) == 0:
                self.errors.append("metadata.title must not be empty")

        if "description" in metadata:
            description = metadata["description"]
            if not isinstance(description, str):
                self.errors.append("metadata.description must be a string")
            elif len(description) == 0:
                self.errors.append("metadata.description must not be empty")

        if "version" in metadata:
            ver = metadata["version"]
            if not isinstance(ver, str):
                self.errors.append(f"metadata.version must be a string, got {type(ver).__name__}")
            elif ver != "0.1":
                self.errors.append(f"version must be '0.1', got '{ver}'")

        if "tags" in metadata:
            tags = metadata["tags"]
            if not isinstance(tags, list):
                self.errors.append("metadata.tags must be a list")
            else:
                if len(tags) == 0:
                    self.errors.append("metadata.tags must have at least one item")
                string_tags = []
                for tag in tags:
                    if not isinstance(tag, str) or len(tag) == 0:
                        self.errors.append("metadata.tags items must be non-empty strings")
                    else:
                        string_tags.append(tag)
                if len(string_tags) != len(set(string_tags)):
                    self.errors.append("metadata.tags must not contain duplicate values")

    def _validate_components(self, components: List[Dict[str, Any]], is_v2: bool = False) -> None:
        """Validate components array.

        In v2 (STAGE_1_TOPOLOGY) format x/y are forbidden on components
        (they live in STAGE_2_LAYOUT.spatial_nodes instead).
        """
        allowed_fields    = ALLOWED_COMPONENT_FIELDS_TOPO if is_v2 else ALLOWED_COMPONENT_FIELDS_FLAT
        required_xy       = not is_v2   # old format requires x/y on each component

        if len(components) > MAX_COMPONENTS:
            self.errors.append(f"too many components: {len(components)} exceeds limit of {MAX_COMPONENTS}")
            return
        seen_ids: Set[str] = set()
        for i, comp in enumerate(components):
            if not isinstance(comp, dict):
                self.errors.append(f"component[{i}] must be a JSON object, got {type(comp).__name__}")
                continue
            if "id" not in comp:
                self.errors.append(f"component[{i}] missing 'id'")
                continue
            comp_id = comp["id"]
            if not isinstance(comp_id, str) or len(comp_id) == 0:
                self.errors.append(f"component[{i}] 'id' must be a non-empty string")
                continue
            if comp_id in seen_ids:
                self.errors.append(f"Duplicate component id: {comp_id}")
                continue
            seen_ids.add(comp_id)
            if not re.match(r'^[A-Z][A-Za-z0-9_]*$', comp_id):
                self.errors.append(f"component '{comp_id}' id violates pattern ^[A-Z][A-Za-z0-9_]*$")

            # Check for unexpected fields (format-dependent)
            extra = set(comp.keys()) - allowed_fields
            if extra:
                self.errors.append(f"component '{comp_id}' has unexpected fields: {sorted(extra)}")

            # v2: x/y must NOT be on topology components
            if is_v2 and ("x" in comp or "y" in comp):
                self.errors.append(
                    f"component '{comp_id}' has x/y in STAGE_1_TOPOLOGY — coordinates belong in STAGE_2_LAYOUT.spatial_nodes"
                )

            # Check required fields (x/y only required in old format)
            required = ["type", "value", "part", "pins"] + (["x", "y"] if required_xy else [])
            for field in required:
                if field not in comp:
                    self.errors.append(f"component '{comp_id}' missing '{field}'")

            # Validate type (only when the field is present to avoid double-reporting)
            comp_type = comp.get("type")
            if "type" in comp and comp_type not in self.valid_component_types:
                self.errors.append(f"component '{comp_id}' invalid type: {comp_type}")

            # Validate value and part are strings
            for field in ["value", "part"]:
                if field in comp and not isinstance(comp[field], str):
                    self.errors.append(f"component '{comp_id}' '{field}' must be a string")

            # Validate x and y are numbers in old format (bool subclasses int — exclude it)
            if not is_v2:
                for field in ["x", "y"]:
                    if field in comp:
                        val = comp[field]
                        if isinstance(val, bool) or not isinstance(val, (int, float)):
                            self.errors.append(
                                f"component '{comp_id}' '{field}' must be a number, got {type(val).__name__}"
                            )

            # Validate pins is dict — only inspect if the field is present (missing
            # already reported above); using get("pins") without a default avoids
            # the double-error that get("pins", {}) produces (empty-dict triggers the
            # "pins must not be empty" error even when the field is absent).
            if "pins" in comp:
                pins = comp["pins"]
                if not isinstance(pins, dict):
                    self.errors.append(f"component '{comp_id}' pins must be dict")
                elif len(pins) == 0:
                    self.errors.append(f"component '{comp_id}' pins must not be empty")
                else:
                    for pin_key, pin_val in pins.items():
                        if not isinstance(pin_val, str):
                            self.errors.append(
                                f"component '{comp_id}' pin '{pin_key}' value must be a string, "
                                f"got {type(pin_val).__name__}"
                            )

    def _validate_nets(self, nets: List[Dict[str, Any]], components: List[Dict[str, Any]]) -> None:
        """Validate nets and connectivity."""
        if len(nets) > MAX_NETS:
            self.errors.append(f"too many nets: {len(nets)} exceeds limit of {MAX_NETS}")
            return
        # Build component pin map; duplicate IDs are excluded so net refs to them
        # fire "unknown component" errors (consistent with the duplicate-ID error
        # already reported by _validate_components).
        comp_id_counts: Dict[str, int] = {}
        for comp in components:
            if not isinstance(comp, dict):
                continue
            cid = comp.get("id")
            if cid:
                comp_id_counts[cid] = comp_id_counts.get(cid, 0) + 1

        comp_pins: Dict[str, Set[str]] = {}
        for comp in components:
            if not isinstance(comp, dict):
                continue
            comp_id = comp.get("id")
            if comp_id and comp_id_counts.get(comp_id, 0) == 1:
                pins_val = comp.get("pins")
                comp_pins[comp_id] = set(pins_val.keys()) if isinstance(pins_val, dict) else set()

        # Track which pins have been resolved to a valid component+pin in at least one net
        used_pins: Set[str] = set()
        # Track valid pin refs across nets for cross-net short detection
        all_pin_refs: Set[str] = set()
        # One short error per pin regardless of how many nets contain it
        reported_shorts: Set[str] = set()
        seen_net_names: Set[str] = set()

        for i, net in enumerate(nets):
            if not isinstance(net, dict):
                self.errors.append(f"net[{i}] must be a JSON object, got {type(net).__name__}")
                continue
            if "name" not in net:
                self.errors.append(f"net[{i}] missing 'name'")
                continue
            net_name = net["name"]

            # Name must be a non-empty string; skip further validation for this net if not
            if not isinstance(net_name, str) or not net_name:
                self.errors.append(f"net[{i}] 'name' must be a non-empty string")
                continue
            elif net_name in seen_net_names:
                self.errors.append(f"Duplicate net name: {net_name}")
                continue
            else:
                seen_net_names.add(net_name)

            # Check for unexpected fields
            extra = set(net.keys()) - ALLOWED_NET_FIELDS
            if extra:
                self.errors.append(f"net '{net_name}' has unexpected fields: {sorted(extra)}")

            # Validate pins field presence and type
            if "pins" not in net:
                self.errors.append(f"net '{net_name}' missing 'pins' field")
                continue
            pins = net["pins"]
            if not isinstance(pins, list):
                self.errors.append(f"net '{net_name}' 'pins' must be a list")
                continue
            if len(pins) < 2:
                self.errors.append(f"net '{net_name}' must have at least 2 pins, got {len(pins)}")
                # Don't skip — still validate pin refs to populate used_pins and
                # avoid false "not connected" errors for pins only in this net.

            # Validate pin references
            seen_in_net: Set[str] = set()
            for pin_ref in pins:
                if not isinstance(pin_ref, str) or not PIN_REF_RE.match(pin_ref):
                    self.errors.append(f"net '{net_name}' invalid pin ref: {pin_ref}")
                    continue

                # Intra-net duplicate check before cross-net check
                if pin_ref in seen_in_net:
                    self.errors.append(f"net '{net_name}' contains duplicate pin ref: {pin_ref}")
                    continue
                seen_in_net.add(pin_ref)

                comp_id, pin_num = pin_ref.split(".", 1)
                if comp_id not in comp_pins:
                    self.errors.append(f"net '{net_name}' references unknown component: {comp_id}")
                elif pin_num not in comp_pins[comp_id]:
                    self.errors.append(
                        f"net '{net_name}' references unknown pin {pin_num} on {comp_id}"
                    )
                else:
                    # Only track cross-net shorts for validated (known comp+pin) refs
                    if pin_ref in all_pin_refs:
                        if pin_ref not in reported_shorts:
                            self.errors.append(
                                f"pin ref {pin_ref} appears in more than one net (electrical short)"
                            )
                            reported_shorts.add(pin_ref)
                    else:
                        all_pin_refs.add(pin_ref)
                    # Mark as used regardless of cross-net short status
                    used_pins.add(pin_ref)

        # Check required power components (only when components is non-empty;
        # empty components is already reported by validate_circuit).
        dict_comps = [c for c in components if isinstance(c, dict)]
        if dict_comps:
            if not any(c.get("type") == "power_vcc" for c in dict_comps):
                self.errors.append("Missing required power_vcc component")
            if not any(c.get("type") == "power_gnd" for c in dict_comps):
                self.errors.append("Missing required power_gnd component")

        # Check all component pins are used (only for components with valid, unique IDs)
        for comp_id, pins in comp_pins.items():
            for pin_id in pins:
                pin_ref = f"{comp_id}.{pin_id}"
                if pin_ref not in used_pins:
                    self.errors.append(f"component pin {pin_ref} not connected to any net")

    def _validate_spatial_layout(
        self,
        spatial_nodes: List[Dict[str, Any]],
        topo_components: List[Dict[str, Any]],
    ) -> None:
        """Validate STAGE_2_LAYOUT.spatial_nodes against the topology component list."""
        topo_ids = {
            c.get("id") for c in topo_components
            if isinstance(c, dict) and isinstance(c.get("id"), str)
        }
        seen_ids: Set[str] = set()
        for i, node in enumerate(spatial_nodes):
            if not isinstance(node, dict):
                self.errors.append(f"spatial_nodes[{i}] must be a JSON object")
                continue
            node_id = node.get("id")
            if not isinstance(node_id, str) or not node_id:
                self.errors.append(f"spatial_nodes[{i}] missing or invalid 'id'")
                continue
            if node_id in seen_ids:
                self.errors.append(f"spatial_nodes: duplicate id '{node_id}'")
                continue
            seen_ids.add(node_id)

            extra = set(node.keys()) - ALLOWED_SPATIAL_NODE_FIELDS
            if extra:
                self.errors.append(f"spatial_nodes '{node_id}' has unexpected fields: {sorted(extra)}")
            if node_id not in topo_ids:
                self.errors.append(f"spatial_nodes '{node_id}' has no matching component in STAGE_1_TOPOLOGY")
            for coord in ("x", "y"):
                if coord in node:
                    val = node[coord]
                    if isinstance(val, bool) or not isinstance(val, (int, float)):
                        self.errors.append(
                            f"spatial_nodes '{node_id}' '{coord}' must be a number, got {type(val).__name__}"
                        )
        # Every topology component must have a spatial node
        for comp_id in topo_ids:
            if comp_id not in seen_ids:
                self.errors.append(f"component '{comp_id}' has no entry in STAGE_2_LAYOUT.spatial_nodes")

    def _validate_forbidden_fields(self, value: Any, path: str = "$") -> None:
        """Reject Step 2-local forbidden supplier/BOM fields anywhere in the circuit."""
        if isinstance(value, dict):
            if path.endswith(".pins"):
                return
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if is_forbidden_field(key):
                    self.errors.append(f"forbidden field at {child_path}: {key}")
                self._validate_forbidden_fields(child, child_path)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                self._validate_forbidden_fields(child, f"{path}[{i}]")

    def get_errors(self) -> List[str]:
        """Return list of validation errors."""
        return self.errors


def load_examples(file_path: Path) -> List[Dict[str, Any]]:
    """Load examples from JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_circuit(circuit: Dict[str, Any], registry_path: Path | None = None) -> List[str]:
    """Validate one circuit and return all validation errors."""
    validator = SchemaValidator(registry_path=registry_path)
    validator.validate_circuit(circuit)
    return validator.get_errors()


def validate_file(file_path: Path) -> Tuple[int, int]:
    """Validate all circuits in a file. Returns (total, valid)."""
    try:
        examples = load_examples(file_path)
    except json.JSONDecodeError as e:
        print(f"Error: {file_path} is not valid JSON: {e}")
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"Error: {file_path} is not valid UTF-8: {e}")
        sys.exit(1)
    except (IOError, OSError) as e:
        print(f"Error: cannot read {file_path}: {e}")
        sys.exit(1)
    if not isinstance(examples, list):
        print(f"Error: {file_path} must contain a JSON array at root level, got {type(examples).__name__}")
        sys.exit(1)
    if len(examples) == 0:
        print(f"Error: no circuits found in {file_path}")
        sys.exit(1)

    validator = SchemaValidator()
    valid_count = 0

    for i, circuit in enumerate(examples):
        if validator.validate_circuit(circuit):
            valid_count += 1
        else:
            title = "UNKNOWN"
            if isinstance(circuit, dict):
                meta = circuit.get("metadata")
                if isinstance(meta, dict):
                    title = meta.get("title") or "UNKNOWN"
            print(f"Circuit {i}: {title}")
            for error in validator.get_errors():
                print(f"  - {error}")

    return len(examples), valid_count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate.py <examples.json>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Error: {file_path} not found")
        sys.exit(1)

    total, valid = validate_file(file_path)
    print(f"\nValidation: {valid}/{total} circuits valid")
    sys.exit(0 if valid == total else 1)
