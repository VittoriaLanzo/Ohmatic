# Ohmatic API Contracts v0.1

This document is the normative reference for all HTTP contracts between Ohmatic services.
All request/response bodies are `application/json`.

---

## 1. POST /v1/generate

**Service:** gateway (public endpoint, port 8080)

Submits a natural-language prompt for circuit generation. Returns immediately with a job ID;
the client must poll `/v1/jobs/{id}/status` for the result.

### Request

```json
{
  "prompt": "555 timer blinking LED at 1 Hz",
  "options": {
    "temperature": 0.4,
    "max_retries": 1,
    "supplier": "local",
    "max_components": 30
  }
}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `prompt` | string | required | Natural language circuit description. |
| `options.temperature` | float [0, 1] | `0.4` | Sampling temperature forwarded to inference. |
| `options.max_retries` | integer | `1` | How many times gateway retries on Tier 1/2 failure. |
| `options.supplier` | string | `"local"` | BOM supplier: `"local"` or `"octopart"`. |
| `options.max_components` | integer | `30` | Soft cap; inference is warned but not hard-blocked. |

### Response 202: Accepted

```json
{
  "job_id": "01HWABCDE9876543210ABCDE01",
  "poll_url": "/v1/jobs/01HWABCDE9876543210ABCDE01/status"
}
```

### Response 400: Bad Request

```json
{ "error": "prompt must not be empty" }
```

### Response 503: Service Unavailable

```json
{ "error": "inference service unavailable" }
```

---

## 2. GET /v1/jobs/{id}/status

**Service:** gateway (public endpoint, port 8080)

Polls the status of an async job. The client should poll at ~500 ms intervals.

### Response 200: Pending

```json
{
  "status": "pending",
  "stage": null,
  "result": null,
  "error": null
}
```

### Response 200: Running

```json
{
  "status": "running",
  "stage": "inference",
  "result": null,
  "error": null
}
```

`stage` is one of `"inference"`, `"drc"`, `"bom"`, or `null` (pending / done / failed states).

### Response 200: Done

```json
{
  "status": "done",
  "stage": null,
  "result": {
    "circuit": { "...": "OhmaticCircuitV01 object" },
    "drc_warnings": ["Missing bypass capacitor near U1"],
    "bom": [],
    "parts_list": [
      {
        "id": "R1",
        "type": "resistor",
        "parts_list_part": "resistor",
        "value": "10k",
        "package": "0603",
        "description": "resistor 10k 0603",
        "is_physical": true,
        "buyable": true,
        "match_status": "local_only"
      }
    ],
    "latency_ms": {
      "inference": 2708,
      "drc": 42,
      "bom": 0,
      "parts_list": 1
    }
  },
  "error": null
}
```

`parts_list` is the deterministic local parts list (see §6 for the `PartsListRow` schema). `bom` is retained as an always-empty field for backward compatibility; supplier resolution is a separate, opt-in step (§6.1) and never populates the job result. The `latency_ms` sub-fields (`inference`, `drc`, `bom`, `parts_list`) are **integer milliseconds**.

### Response 200: Failed

```json
{
  "status": "failed",
  "stage": null,
  "result": null,
  "error": {
    "code": "tier1_validation_failed",
    "message": "Component IDs are not unique: R1 appears twice"
  }
}
```

#### error.code values

| `error.code` | Cause |
|---|---|
| `tier1_validation_failed` | Circuit failed Tier 1 schema/structural check after all retries exhausted. |
| `tier2_validation_failed` | Circuit failed Tier 2 geometric check after all retries exhausted. |
| `grammar_timeout` | Inference constrained decoding timed out producing a valid circuit. |
| `unsupported_schema_version` | `metadata.version` returned by inference is not `"0.1"`. |
| `inference_unavailable` | Inference service unreachable; gateway returned 503. |

> **Error shape note:** Synchronous gateway errors (400, 503 on `POST /v1/generate`) and internal service errors (`POST /infer` 422) use a flat string form: `{ "error": "message" }`. Async job failures use a structured object: `{ "code": "...", "message": "..." }`. These are two different response surfaces; clients must handle both.

### Response 404: Not Found

```json
{ "error": "job_not_found" }
```

---

## 3. GET /health

**Service:** all four services (gateway :8080, inference :8001, verifier :8002, enricher :8003)

Liveness probe for Docker health checks and load balancer readiness.

### Response 200: OK

```json
{ "status": "ok" }
```

No authentication required.

---

## 4. POST /infer

**Service:** inference (internal, port 8001)

Generates an `OhmaticCircuitV01` object from a natural-language prompt.

### Request

```json
{
  "prompt": "555 timer blinking LED at 1 Hz",
  "temperature": 0.4
}
```

### Response 200: OK

```json
{
  "circuit": {
    "metadata": { "title": "555 Timer Astable", "description": "...", "version": "0.1", "tags": ["timer"] },
    "components": [ "..." ],
    "nets": [ "..." ]
  },
  "raw_tokens": 847,
  "duration_ms": 2708
}
```

### Response 422: Grammar Timeout

Returned when constrained decoding times out before producing a valid circuit.

```json
{
  "error": "grammar_timeout",
  "partial": "{\"metadata\": {\"title\": \"555 Timer\", ..."
}
```

---

## 5. POST /verify

**Service:** verifier (internal, port 8002)

Validates an `OhmaticCircuitV01` object against the three-tier DRC rule set (see [§7](#7-verifier-tier-model)).

### Request

```json
{
  "circuit": { "...": "OhmaticCircuitV01 object" }
}
```

### Response 200: OK

Returned for circuits that pass Tier 1 and Tier 2 (errors is empty). Tier 3 issues
are reported as warnings; the gateway surfaces these in `result.drc_warnings`.

```json
{
  "circuit": { "...": "OhmaticCircuitV01 object (coordinates normalized to 0-300)" },
  "warnings": ["Missing bypass capacitor near U1 (Tier 3)"],
  "errors": []
}
```

`errors` is always `[]` on a 200. A non-empty errors array is always signalled via HTTP 422. Gateway reads: 200 → pass, 422 → Tier 1/2 failure.

### Response 400: Bad Request

```json
{ "error": "missing 'circuit' field" }
```

Request body absent, not valid JSON, or missing the `circuit` field.

### Response 422: Parse Error (circuit field present but undeserializable)

Two sub-cases, distinguished by rule ID prefix:

**T1-PARSE-SERDE**: `circuit` JSON structure is valid but cannot be coerced into `OhmaticCircuitV01` (missing required field, wrong type, deny_unknown_fields violation on a Component or Net). Not retry-able; the model produced malformed JSON.

```json
{
  "errors": ["[T1-PARSE-SERDE] failed to deserialise circuit: missing field `nets`"],
  "warnings": []
}
```

**T1-PARSE-REGISTRY**: `circuit` deserialises successfully but a component carries a `type` string absent from the component registry. Retry-able; the model hallucinated an unknown component type.

```json
{
  "errors": ["[T1-PARSE-REGISTRY] unknown component type 'unknown_widget' on component 'U1'"],
  "warnings": []
}
```

### Response 422: Validation Error (Tier 1 or Tier 2)

```json
{
  "errors": ["[T1-04] Duplicate component id: R1"],
  "warnings": []
}
```

`validate()` found structural violations. Each entry in `errors` has format `"[rule_id] message"`. `warnings` is always `[]` on 422.

---

## 6. POST /enrich

**Service:** enricher (internal, port 8003)

Builds a deterministic local parts list for a verified circuit: one row per component,
derived entirely from `verifier/config/component_registry.toml`. No network calls, no
supplier lookups, no pricing. The output is byte-stable for a given circuit, so it can be
cached and diffed.

### Request

```json
{
  "circuit": { "...": "OhmaticCircuitV01 object" }
}
```

### Response 200: OK

Returns one `PartsListRow` per component in the same order as `circuit.components`.

```json
[
  {
    "id": "R1",
    "type": "resistor",
    "parts_list_part": "resistor",
    "value": "10k",
    "package": "0603",
    "description": "resistor 10k 0603",
    "is_physical": true,
    "buyable": true,
    "match_status": "local_only"
  },
  {
    "id": "VCC1",
    "type": "power_vcc",
    "parts_list_part": "power_vcc",
    "value": "5V",
    "package": "VCC",
    "description": "power_vcc 5V VCC",
    "is_physical": false,
    "buyable": false,
    "match_status": "local_only"
  }
]
```

### PartsListRow Schema

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Component ID (e.g. `"R1"`). |
| `type` | string | Component type from the circuit (e.g. `"resistor"`). |
| `parts_list_part` | string | Canonical part category from the component registry. |
| `value` | string | Component value (e.g. `"10k"`); `""` when not set. |
| `package` | string | Package/footprint from the component `part` field; `""` when not set. |
| `description` | string | Human-readable summary: `parts_list_part value package`, space-joined, blanks dropped. |
| `is_physical` | boolean | `true` for orderable parts; `false` for schematic-only symbols (power, ground). |
| `buyable` | boolean | Whether the row can be ordered. Equal to `is_physical` in Stage 0. |
| `match_status` | string | Resolution state. Always `"local_only"` from the registry-only enricher. |

### Response 422: Unknown component type

Returned when a component `type` has no entry in the component registry.

```json
{ "error": "unknown component type for parts_list: 'frobnicator'" }
```

### 6.1 Supplier resolution (separate step)

Supplier matching, referral links, and any pricing are handled by the procurement layer
(`POST /v1/procurement/matches`), which consumes a parts list and returns disclosed
link-outs. By design the enricher never writes `supplier`, `mpn`, `price`, `url`, or any
affiliate field onto parts-list rows or circuit JSON.

---

## 7. Verifier Tier Model

The verifier applies rules in three tiers. Tiers are applied sequentially; a Tier 1 failure
prevents Tier 2 checks from running, and so on.

| Tier | Category | Gateway behaviour | Example rules |
|------|----------|-------------------|---------------|
| **Tier 1** | Schema violations | Return 422, increment retry counter | Duplicate component IDs; duplicate net names; invalid component type; missing required pin; no VCC component; no GND component |
| **Tier 2** | Geometric violations | Normalize coordinates and push-apart collisions (max 20 iterations). Always returns 200. Unresolvable collisions appear as `[T2-02]` entries in the `warnings` array; the gateway does not retry Tier 2. | Component bounding-box collision; component placed outside the 0-300 canvas after normalization |
| **Tier 3** | Electrical correctness | Return 200 with `drc_warnings` populated | LED without series resistor; IC power pin unconnected; missing bypass capacitor near IC; floating MOSFET gate; reverse-polarity capacitor |

- **Tier 1 → 422:** the gateway may retry inference up to `options.max_retries` times
  before returning a `"failed"` job status to the client.
- **Tier 2 → always 200:** the verifier corrects what it can. Unresolvable collisions produce a
  `DRC_WARNING` but the circuit is still accepted. The gateway never retries on Tier 2 warnings.
- **Tier 3 → 200 + `drc_warnings`:** the circuit is accepted and the client sees warnings in
  `result.drc_warnings`. No retry is triggered.

The Tier 3 rule catalog will be specified in Stage 1. The examples above are illustrative.

**Implemented types (Stage 0):** `power_vee`, `relay`, and all other types listed in the schema enum are accepted by the verifier. The schema enum and `verifier/config/component_registry.toml` are kept in sync; the registry is the authoritative source at runtime.

---

## 8. Schema Versioning Dispatch

The gateway reads `metadata.version` from the circuit returned by inference to select the
correct verifier rule set. This allows multiple schema versions to coexist on a single
running instance.

| `metadata.version` | Action |
|--------------------|--------|
| `"0.1"` | Apply full Tier 1-3 rule set against `shared/schema/circuit_v01.json`. |
| Any other value | Job fails with `error.code = "unsupported_schema_version"` (see §2 failed state). |

**Dispatch example:**

```text
POST /v1/generate → inference returns circuit with metadata.version = "0.1"
→ gateway dispatches to verifier with circuit_v01 rule set
→ verifier returns { warnings: [], errors: [] }
→ gateway proceeds to enricher
```

**Unknown version rejection example:**

```text
POST /v1/generate → inference returns circuit with metadata.version = "99.0"
→ gateway sets job to "failed" with error.code = "unsupported_schema_version"
→ GET /v1/jobs/{id}/status returns: { "status": "failed", "error": { "code": "unsupported_schema_version", "message": "metadata.version \"99.0\" is not supported" } }
```

Forward-compatible: adding `circuit_v02.json` with a new rule set requires no gateway changes.

> **Schema limitation:** JSON Schema draft-07 cannot enforce uniqueness of `nets[].name` across
> the array. Net-name uniqueness is enforced by `dataset/validate.py` and by the verifier's Tier 1
> rule set. Do not rely solely on `jsonschema.validate()` for this constraint.

---

## 9. Extending the Component Type Enum

`ComponentType` is a **transparent string newtype**; it is not a Rust enum. To add a new component type (e.g. `relay_solid_state`):

1. Add the new string to `circuit_v01.json` `components[].type.enum` (keeps the schema in sync with the registry).
2. Add an entry to `verifier/config/component_registry.toml` (`bbox`, `ref_prefix`, `description` fields).
3. Optionally add a `pub const` to the `component_types` module in `shared/ohmatic-types/src/circuit.rs` for use in rule code; no other Rust change is required.
4. Add an example circuit using the new type to `dataset/examples.json`.
5. Update the Tier 3 DRC rules in `shared/docs/contracts.md` if new electrical rules apply.
6. Bump `metadata.version` only when introducing breaking schema changes (adding a field to components, changing a required field type). Adding a new type to the enum is additive and non-breaking; no version bump required.

> **`/health` versioning note:** The `/health` endpoint on all four services is intentionally unversioned (no `/v1/` prefix). It is a liveness probe, not an API resource. All other endpoints are versioned under `/v1/`.

> **`additionalProperties` policy:** The JSON schema allows extra fields at the circuit root (`additionalProperties: true`) to support dataset annotation fields (e.g. `tier3_reviewed`). The `metadata` object is also open to allow tooling extensions. Only `Component` and `Net` objects are strict (`additionalProperties: false`). Do not rely on schema validation alone to reject unknown fields at the root or metadata level.
