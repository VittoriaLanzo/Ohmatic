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
  "job_id": "01HWABCDE9876543210ABCDE",
  "poll_url": "/v1/jobs/01HWABCDE9876543210ABCDE/status"
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

### Response 404 — Not Found

```json
{ "error": "job_not_found" }
```

---

## 3. POST /infer

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

## 4. POST /verify

**Service:** verifier (internal, port 8002)

Validates an `OhmaticCircuitV01` object against the three-tier DRC rule set (see [§6](#6-verifier-tier-model)).

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

If `errors` is **non-empty**, the gateway treats this as a Tier 1/2 failure and returns 422
to the client (or retries, up to `options.max_retries`).

### Response 422 — Validation Error (Tier 1 or Tier 2)

```json
{
  "errors": ["Component IDs are not unique: R1 appears twice"],
  "warnings": []
}
```

---

## 5. POST /enrich

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

## 6. Verifier Tier Model

The verifier applies rules in three tiers. Tiers are applied sequentially; a Tier 1 failure
prevents Tier 2 checks from running, and so on.

| Tier | Category | Gateway behaviour | Example rules |
|------|----------|-------------------|---------------|
| **Tier 1** | Schema violations | Return 422, increment retry counter | Duplicate component IDs; invalid component type; missing required pin; no VCC component; no GND component |
| **Tier 2** | Geometric violations | Return 422, increment retry counter | Component bounding-box collision; component placed outside the 0–300 canvas after normalization |
| **Tier 3** | Electrical correctness | Return 200 with `drc_warnings` populated | LED without series resistor; transistor base with no bias resistor; IC power pin unconnected; missing bypass capacitor near IC |

- **Tier 1 and Tier 2 → 422:** the gateway may retry inference up to `options.max_retries` times
  before returning a `"failed"` job status to the client.
- **Tier 3 → 200 + `drc_warnings`:** the circuit is accepted and the client sees warnings in
  `result.drc_warnings`. No retry is triggered.

Full Tier 3 rule catalog: see `OHMATIC_BACKEND_BUILD_PLAN.md` section 3.1.

---

## 7. Schema Versioning Dispatch

The gateway reads `metadata.version` from the circuit returned by inference to select the
correct verifier rule set. This allows multiple schema versions to coexist on a single
running instance.

| `metadata.version` | Action |
|--------------------|--------|
| `"0.1"` | Apply full Tier 1–3 rule set against `shared/schema/circuit_v01.json`. |
| Any other value | Return 422 with `{ "error": "unsupported_schema_version" }`. |

**Dispatch example:**

```json
POST /v1/generate → inference returns circuit with metadata.version = "0.1"
→ gateway dispatches to verifier with circuit_v01 rule set
→ verifier returns { warnings: [], errors: [] }
→ gateway proceeds to enricher
```

**Unknown version rejection example:**

```json
POST /v1/generate → inference returns circuit with metadata.version = "99.0"
→ gateway returns 422: { "error": "unsupported_schema_version" }
```

This dispatch design is forward-compatible: adding `circuit_v02.json` and a corresponding
verifier rule set requires no changes to the gateway dispatch table structure.
