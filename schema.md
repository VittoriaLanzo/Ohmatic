# Ohmatic Circuit Schema v0.1 (two-stage)

> The runtime system prompt is assembled by `shared/prompt_builder.py`
> (`build_system_prompt()`), which is the single source of truth used by both the
> dataset builder and eval/inference. This file documents the same format for humans.

## Overview

A circuit is **one JSON object** with exactly three top-level keys:
`metadata`, `STAGE_1_TOPOLOGY`, `STAGE_2_LAYOUT`. The model emits **minified** JSON.

## Top-level structure

```json
{
  "metadata": {"title": "...", "description": "...", "version": "0.1", "tags": ["..."]},
  "STAGE_1_TOPOLOGY": {
    "components": [
      {"id": "R1", "type": "resistor", "value": "330", "part": "0603",
       "pins": {"1": "VCC", "2": "N1"}}
    ],
    "nets": [
      {"name": "VCC", "pins": ["VCC1.1", "R1.1"]}
    ]
  },
  "STAGE_2_LAYOUT": {
    "spatial_nodes": [
      {"id": "R1", "x": 40, "y": 0}
    ]
  }
}
```

### STAGE_1_TOPOLOGY: electrical connectivity
- **components[]**: `id` (unique), `type` (must be a key in the component registry),
  `value`, `part`, and `pins`, a map of `pin_name -> net_name`.
- **nets[]**: `name` and `pins`, a list of `"<component_id>.<pin_name>"` references.

### STAGE_2_LAYOUT: physical placement
- **spatial_nodes[]**: exactly one `{id, x, y}` per component; canvas coordinates 0-300.

## Constraints
1. Component `id`s are unique; every component has a matching `spatial_node`.
2. Every net pin `"<id>.<pin>"` references an existing component pin.
3. Nets named `"VCC"` and `"GND"` must exist.
4. Each `type` must be a key in the **component registry** (`verifier/config/component_registry.toml`).
5. The circuit must satisfy every rule in the **ERC catalog** (`verifier/config/erc_rules_catalog.json`).

## Example (minified)

```json
{"metadata":{"title":"LED indicator","description":"LED with series resistor on 5V","version":"0.1","tags":["led","basic"]},"STAGE_1_TOPOLOGY":{"components":[{"id":"VCC1","type":"power_vcc","value":"5V","part":"PWR","pins":{"1":"VCC"}},{"id":"R1","type":"resistor","value":"330","part":"0603","pins":{"1":"VCC","2":"N1"}},{"id":"LED1","type":"led","value":"RED","part":"0805","pins":{"A":"N1","K":"GND"}},{"id":"GND1","type":"power_gnd","value":"0V","part":"PWR","pins":{"1":"GND"}}],"nets":[{"name":"VCC","pins":["VCC1.1","R1.1"]},{"name":"N1","pins":["R1.2","LED1.A"]},{"name":"GND","pins":["LED1.K","GND1.1"]}]},"STAGE_2_LAYOUT":{"spatial_nodes":[{"id":"VCC1","x":0,"y":0},{"id":"R1","x":40,"y":0},{"id":"LED1","x":90,"y":0},{"id":"GND1","x":130,"y":0}]}}
```

## Version History
- **v0.1**: two-stage representation: STAGE_1_TOPOLOGY (electrical) + STAGE_2_LAYOUT (placement).
