"""
prompt_builder.py - single source of truth for the Ohmatic system prompt.
================================================================================
ONE function builds the standardized system prompt from the canonical config:

    verifier/config/component_registry.toml   ← every component type (the registry)
    verifier/config/erc_rules_catalog.json    ← every ERC rule (must all pass)

Both the dataset builder AND the eval/inference path import build_system_prompt()
so the prompt the model is TRAINED on is byte-identical to the prompt it is
EVALUATED/served with. (Previously the dataset embedded a stale flat schema + a
per-request registry subset while eval sent no system prompt at all, so the model
saw three different contexts. This module makes that drift impossible.)

The prompt is fully minified (the model emits minified JSON, so the examples match
the target and the token budget stays small, ~5.6k tokens with the full registry
and full rule catalog).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY_TOML = _REPO_ROOT / "verifier" / "config" / "component_registry.toml"
_RULES_JSON = _REPO_ROOT / "verifier" / "config" / "erc_rules_catalog.json"

# Registry fields the model actually needs: what the type is, its reference-designator
# prefix (for id naming), and its bounding box (informs STAGE_2 placement spacing).
_REGISTRY_FIELDS = ("description", "ref_prefix", "bbox")
# Full rule record: code + severity + the constraint (message) + the rationale (why)
# + the fix (repair). All of it fits in budget and is useful training signal.
_RULE_FIELDS = ("code", "severity", "message", "why", "repair")

_SCHEMA = (
    "A circuit is ONE JSON object with exactly three top-level keys: "
    "metadata, STAGE_1_TOPOLOGY, STAGE_2_LAYOUT.\n"
    'metadata: {"title","description","version":"0.1","tags":[...]}\n'
    "STAGE_1_TOPOLOGY (electrical connectivity): "
    '{"components":[{"id","type","value","part","pins":{"<pin_name>":"<net_name>"}}],'
    '"nets":[{"name","pins":["<component_id>.<pin_name>",...]}]}\n'
    "STAGE_2_LAYOUT (physical placement): "
    '{"spatial_nodes":[{"id":"<component_id>","x":<int>,"y":<int>}]} '
    "— exactly one node per component, canvas coordinates 0-300.\n"
    "Constraints: component ids are unique; every component has a spatial_node; every "
    'net pin "<id>.<pin>" references an existing component pin; nets named "VCC" and '
    '"GND" must exist; each component "type" MUST be a key in the COMPONENT REGISTRY '
    "below; choose ids using the registry ref_prefix."
)

# A minimal, correct, minified example so the model sees the exact target shape.
_EXAMPLE = (
    '{"metadata":{"title":"LED indicator","description":"LED with series resistor on 5V",'
    '"version":"0.1","tags":["led","basic"]},"STAGE_1_TOPOLOGY":{"components":['
    '{"id":"VCC1","type":"power_vcc","value":"5V","part":"PWR","pins":{"1":"VCC"}},'
    '{"id":"R1","type":"resistor","value":"330","part":"0603","pins":{"1":"VCC","2":"N1"}},'
    '{"id":"LED1","type":"led","value":"RED","part":"0805","pins":{"A":"N1","K":"GND"}},'
    '{"id":"GND1","type":"power_gnd","value":"0V","part":"PWR","pins":{"1":"GND"}}],'
    '"nets":[{"name":"VCC","pins":["VCC1.1","R1.1"]},{"name":"N1","pins":["R1.2","LED1.A"]},'
    '{"name":"GND","pins":["LED1.K","GND1.1"]}]},"STAGE_2_LAYOUT":{"spatial_nodes":['
    '{"id":"VCC1","x":0,"y":0},{"id":"R1","x":40,"y":0},{"id":"LED1","x":90,"y":0},'
    '{"id":"GND1","x":130,"y":0}]}}'
)

_PREAMBLE = (
    "You are Ohmatic, an AI PCB schematic generator. Output ONLY a single minified JSON "
    "object in the Ohmatic two-stage circuit format described below. No prose, no markdown "
    "fences, no comments — only the raw JSON."
)


def _mini(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


@lru_cache(maxsize=1)
def _registry_block() -> str:
    reg = tomllib.loads(_REGISTRY_TOML.read_text(encoding="utf-8"))
    reg.pop("defaults", None)
    compact = {t: {k: v for k, v in d.items() if k in _REGISTRY_FIELDS}
               for t, d in reg.items()}
    return _mini(compact)


@lru_cache(maxsize=1)
def _rules_block() -> str:
    cat = json.loads(_RULES_JSON.read_text(encoding="utf-8"))
    trimmed = [{k: r[k] for k in _RULE_FIELDS if k in r} for r in cat]
    return _mini(trimmed)


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    """Return the standardized Ohmatic system prompt (deterministic, minified)."""
    return "\n\n".join([
        _PREAMBLE,
        "=== CIRCUIT SCHEMA ===\n" + _SCHEMA + "\nExample: " + _EXAMPLE,
        '=== COMPONENT REGISTRY (every available type; use only these "type" values) ===\n'
        + _registry_block(),
        "=== ERC RULES (the generated circuit must satisfy ALL of these) ===\n"
        + _rules_block(),
    ])


if __name__ == "__main__":
    sp = build_system_prompt()
    print(f"system prompt: {len(sp)} chars")
    print(sp[:1200])
