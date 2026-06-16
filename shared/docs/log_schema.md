# Ohmatic Log Schema v0.1

> **Normative**: all three services (gateway, inference, verifier) MUST emit
> newline-delimited JSON logs matching this schema. Log aggregators (e.g., Loki, CloudWatch)
> depend on the field names being stable.

---

## Required Fields

Every log line is a single JSON object. The following five fields are **required** on every
line emitted by any service.

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string (ISO-8601 UTC) | When the event occurred (example: `2026-05-23T14:32:01.004Z`). Always UTC, always millisecond precision or better. |
| `request_id` | string (ULID) | Unique ID for the inbound request, propagated end-to-end from the gateway across all downstream calls. Format: 26-char ULID, e.g. `"01HWABCDE1234567890ABCDEF0"`. |
| `service` | string enum | One of `"gateway"`, `"inference"`, `"verifier"`. |
| `level` | string enum | One of `"debug"`, `"info"`, `"warn"`, `"error"`. |
| `message` | string | Human-readable description of the event. Must not be empty. |

> **Note:** For log lines that are not associated with an inbound request (e.g. service startup, scheduled tasks), `request_id` should be set to a generated ULID scoped to that operation. Health-check probe log lines may omit `request_id`.

---

## Service-Specific Optional Fields

Each service may include additional fields. These are **not** required but should be consistent
within a service.

### gateway

| Field | Type | Notes |
|-------|------|-------|
| `job_id` | string | ULID of the async job created for this request. |
| `http_method` | string | e.g. `"POST"`, `"GET"`. |
| `http_path` | string | e.g. `"/v1/generate"`. |
| `http_status` | integer | HTTP response status code. |
| `latency_ms` | integer | End-to-end request latency in milliseconds. |
| `parts_list_entries` | integer | Number of rows in the deterministic local parts list (one per component). |
| `buyable_parts` | integer | Rows flagged `buyable: true` (physical, orderable components). |
| `non_physical_symbols` | integer | Rows flagged `is_physical: false` (power, ground, and other schematic-only symbols). |

### inference

| Field | Type | Notes |
|-------|------|-------|
| `model` | string | Model identifier, e.g. `"ohmatic-v0.1-finetune"`. |
| `raw_tokens` | integer | Number of tokens generated. |
| `duration_ms` | integer | Inference wall-clock time in ms. |
| `temperature` | number | Sampling temperature used. |

### verifier

| Field | Type | Notes |
|-------|------|-------|
| `tier` | integer | Tier that triggered (1, 2, or 3). |
| `warnings_count` | integer | Number of Tier 3 DRC warnings emitted. |
| `errors_count` | integer | Number of Tier 1/2 errors that caused 422. |
| `circuit_id` | string | `metadata.title` or a hash for traceability. |

---

## Example Log Lines

**gateway**, job accepted:
```json
{"timestamp":"2026-05-23T14:32:01.004Z","request_id":"01HWABCDE1234567890ABCDEF0","service":"gateway","level":"info","message":"Job accepted","job_id":"01HWABCDE9876543210ABCDEF0","http_method":"POST","http_path":"/v1/generate","http_status":202,"latency_ms":3}
```

**inference**, generation complete:
```json
{"timestamp":"2026-05-23T14:32:03.712Z","request_id":"01HWABCDE1234567890ABCDEF0","service":"inference","level":"info","message":"Circuit generated","model":"ohmatic-v0.1-finetune","raw_tokens":847,"duration_ms":2708,"temperature":0.4}
```

**verifier**, Tier 3 warning emitted:
```json
{"timestamp":"2026-05-23T14:32:03.901Z","request_id":"01HWABCDE1234567890ABCDEF0","service":"verifier","level":"warn","message":"Tier 3 DRC warning: missing bypass capacitor near U1","tier":3,"warnings_count":1,"errors_count":0,"circuit_id":"555 Timer Astable Oscillator"}
```

**gateway**, parts list built:
```json
{"timestamp":"2026-05-23T14:32:04.210Z","request_id":"01HWABCDE1234567890ABCDEF0","service":"gateway","level":"info","message":"Parts list built","parts_list_entries":8,"buyable_parts":6,"non_physical_symbols":2}
```

---

## Implementation Notes (Stage 1 Production Target)

> **Stage 0 note:** The Stage 0 stubs emit minimal stdout only. The logging contract below applies to the Stage 1 production implementation.

- **Rust services** (gateway, verifier; Stage 1 target; Stage 0 uses Python stubs): use
  [`tracing`](https://docs.rs/tracing) with [`tracing-subscriber`](https://docs.rs/tracing-subscriber)
  configured for JSON output via `tracing_subscriber::fmt().json().init();`. Set `RUST_LOG=info` in production.

- **Python service** (inference): use [`structlog`](https://www.structlog.org/) with
  `structlog.configure(processors=[structlog.processors.JSONRenderer()])`.
  Inject `request_id` at request entry via `structlog.contextvars.bind_contextvars(request_id=...)`.

- **request_id propagation**: gateway generates the ULID on receipt and forwards it as the `X-Request-ID` HTTP header (normative; all internal calls MUST include this header). Each downstream service reads `X-Request-ID` from the incoming request and binds it to its log context.
