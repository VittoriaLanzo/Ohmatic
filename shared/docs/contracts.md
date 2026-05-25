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

### Response 202 — Accepted

```json
{
  "job_id": "01HWABCDE9876543210ABCDE01",
  "poll_url": "/v1/jobs/01HWABCDE9876543210ABCDE01/status"
}
```

### Response 400 — Bad Request

```json
{ "error": "prompt must not be empty" }
```

### Response 503 — Service Unavailable

```json
{ "error": "inference service unavailable" }
```

---

## 2. GET /v1/jobs/{id}/status

**Service:** gateway (public endpoint, port 8080)

Polls the status of an async job. The client should poll at ~500 ms intervals.

### Response 200 — Pending

```json
{
  "status": "pending",
  "stage": null,
  "result": null,
  "error": null
}
```

### Response 200 — Running

```json
{
  "status": "running",
  "stage": "inference",
  "result": null,
  "error": null
}
```

`stage` is one of `"inference"`, `"drc"`, `"bom"`.

### Response 200 — Done

```json
{
  "status": "done",
  "stage": null,
  "result": {
    "circuit": { "...": "OhmaticCircuitV01 object" },
    "drc_warnings": ["Missing bypass capacitor near U1"],
    "bom": [
      {
        "id": "R1",
        "mpn": "RC0603FR-0710KL",
        "description": "Resistor 10kΩ 1% 0603",
        "price_usd": 0.01,
        "url": "https://octopart.com/...",
        "mpn_found": true
      }
    ],
    "latency_ms": {
      "inference": 2708,
      "drc": 42,
      "bom": 180
    }
  },
  "error": null
}
```

The `latency_ms` sub-fields (`inference`, `drc`, `bom`) are **integer milliseconds**.

### Response 200 — Failed

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

> **Error shape note:** Synchronous gateway errors (400, 503 on `POST /v1/generate`) and internal service errors (`POST /infer` 422) use a flat string form: `{ "error": "message" }`. Async job failures use a structured object: `{ "code": "...", "message": "..." }`. These are two different response surfaces — clients must handle both.

### Response 404 — Not Found

```json
{ "error": "job_not_found" }
```

---

## 3. GET /health

**Service:** all four services (gateway :8080, inference :8001, verifier :8002, enricher :8003)

Liveness probe for Docker health checks and load balancer readiness.

### Response 200 — OK

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

### Response 200 — OK

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

### Response 422 — Grammar Timeout

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

### Response 200 — OK

Returned for circuits that pass Tier 1 and Tier 2 (errors is empty). Tier 3 issues
are reported as warnings; the gateway surfaces these in `result.drc_warnings`.

```json
{
  "circuit": { "...": "OhmaticCircuitV01 object (coordinates normalized to 0–300)" },
  "warnings": ["Missing bypass capacitor near U1 (Tier 3)"],
  "errors": []
}
```

`errors` is always `[]` on a 200. A non-empty errors array is always signalled via HTTP 422. Gateway reads: 200 → pass, 422 → Tier 1/2 failure.

### Response 400 — Bad Request

```json
{ "error": "missing 'circuit' field" }
```

Request body absent, not valid JSON, or missing the `circuit` field.

### Response 422 — Parse Error (circuit field present but undeserializable)

`circuit` is present but cannot be deserialised into `OhmaticCircuitV01` (unknown type string, missing field, type mismatch). Fires before `validate()`; rule ID `T1-PARSE` (see §7).

```json
{
  "errors": ["[T1-PARSE] failed to deserialise circuit: unknown variant `unknown_widget` for enum ComponentType"],
  "warnings": []
}
```

### Response 422 — Validation Error (Tier 1 or Tier 2)

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

Resolves MPNs and pricing for every component in a circuit.

### Request

```json
{
  "circuit": { "...": "OhmaticCircuitV01 object" },
  "supplier": "local"
}
```

### Response 200 — OK

Returns one `BomEntry` per component in the same order as `circuit.components`.

```json
[
  {
    "id": "R1",
    "mpn": "RC0603FR-0710KL",
    "description": "Resistor 10kΩ 1% 0603",
    "price_usd": 0.01,
    "url": "https://octopart.com/rc0603fr-0710kl-yageo-20756462",
    "mpn_found": true
  },
  {
    "id": "VCC1",
    "mpn": null,
    "description": "Power symbol — no physical part",
    "price_usd": null,
    "url": null,
    "mpn_found": false
  }
]
```

### BomEntry Schema

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Component ID (e.g. `"R1"`). |
| `mpn` | string \| null | Manufacturer part number; `null` if not found. |
| `description` | string | Human-readable part description. |
| `price_usd` | float \| null | Unit price in USD; `null` if unavailable. |
| `url` | string \| null | Datasheet or supplier URL; `null` if unavailable. |
| `mpn_found` | boolean | `true` if an MPN was resolved. |

---

## 7. Verifier Tier Model

The verifier applies rules in three tiers. Tiers are applied sequentially; a Tier 1 failure
prevents Tier 2 checks from running, and so on.

| Tier | Category | Gateway behaviour | Example rules |
|------|----------|-------------------|---------------|
| **Tier 1** | Schema violations | Return 422, increment retry counter | Duplicate component IDs; duplicate net names; invalid component type; missing required pin; no VCC component; no GND component |
| **Tier 2** | Geometric violations | Normalize coordinates and push-apart collisions (max 20 iterations). Return 200 if all collisions resolved. If any collision remains unresolvable, return 200 + `DRC_WARNING` (gateway does not retry Tier 2). | Component bounding-box collision; component placed outside the 0–300 canvas after normalization |
| **Tier 3** | Electrical correctness | Return 200 with `drc_warnings` populated | LED without series resistor; transistor base with no bias resistor; IC power pin unconnected; missing bypass capacitor near IC |

- **Tier 1 → 422:** the gateway may retry inference up to `options.max_retries` times
  before returning a `"failed"` job status to the client.
- **Tier 2 → always 200:** the verifier corrects what it can. Unresolvable collisions produce a
  `DRC_WARNING` but the circuit is still accepted. The gateway never retries on Tier 2 warnings.
- **Tier 3 → 200 + `drc_warnings`:** the circuit is accepted and the client sees warnings in
  `result.drc_warnings`. No retry is triggered.

The Tier 3 rule catalog will be specified in Stage 1. The examples above are illustrative.

**Known Stage 0 enum gaps (deferred to Stage 1):**
- Negative supply rails (e.g. VEE, −15 V) are typed as `power_vcc` — a `power_vee` type will be added in Stage 1.
- Relay coils are typed as `connector` — a `relay` type will be added in Stage 1 to enable flyback-diode DRC rules.

---

## 8. Schema Versioning Dispatch

The gateway reads `metadata.version` from the circuit returned by inference to select the
correct verifier rule set. This allows multiple schema versions to coexist on a single
running instance.

| `metadata.version` | Action |
|--------------------|--------|
| `"0.1"` | Apply full Tier 1–3 rule set against `shared/schema/circuit_v01.json`. |
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

To add a new component type (e.g. `relay`, `power_vee`):

1. Add the new string to `circuit_v01.json` `components[].type.enum`.
2. Add the corresponding variant to `ComponentType` in `shared/ohmatic-types/src/circuit.rs`.
3. Add an example circuit using the new type to `dataset/examples.json`.
4. Update the Tier 3 DRC rules in `shared/docs/contracts.md` if new electrical rules apply.
5. Bump `metadata.version` only when introducing breaking schema changes.
