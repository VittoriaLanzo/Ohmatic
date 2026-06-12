import type { OhmaticCircuitV01 } from "./circuit";

export type Supplier = "local" | "octopart";

export type GenerateOptions = {
  temperature?: number;
  max_retries?: number;
  supplier?: Supplier;
  max_components?: number;
};

export type GenerateRequest = {
  prompt: string;
  options?: GenerateOptions;
};

export type GenerateAcceptedResponse = {
  job_id: string;
  poll_url: string;
};

export type BomEntry = {
  id: string;
  mpn: string | null;
  description: string;
  price_usd: number | null;
  url: string | null;
  mpn_found: boolean;
};

export type LatencyMs = {
  inference: number;
  drc: number;
  bom?: number;
  parts_list?: number;
};

/** Deterministic local parts list row (supplier-free by design). */
export type PartsListRow = {
  id: string;
  type: string;
  parts_list_part: string;
  value: string;
  package: string;
  description: string;
  is_physical: boolean;
  buyable: boolean;
  match_status: string;
};

export type GenerateResult = {
  circuit: OhmaticCircuitV01;
  drc_warnings: string[];
  bom?: BomEntry[];
  parts_list?: PartsListRow[];
  latency_ms: LatencyMs;
};

export type JobStage = "t5" | "generate" | "verify" | "inference" | "drc" | "bom";

export type JobErrorCode =
  | "tier1_validation_failed"
  | "tier2_validation_failed"
  | "grammar_timeout"
  | "unsupported_schema_version"
  | "inference_unavailable"
  | (string & {});

export type JobError = {
  code: JobErrorCode;
  message: string;
};

export type JobPending = {
  status: "pending";
  stage: null;
  result: null;
  error: null;
};

export type JobRunning = {
  status: "running";
  progress?: number | null;
  loops?: number;
  stage: JobStage;
  result: null;
  error: null;
};

export type JobDone = {
  status: "done";
  stage: null;
  result: GenerateResult;
  error: null;
};

export type JobFailed = {
  status: "failed";
  stage: null;
  result: null;
  error: JobError;
};

export type JobStatusResponse = JobPending | JobRunning | JobDone | JobFailed;

export type HealthResponse = {
  status: "ok";
};

export type ClientErrorSource = "submit" | "poll" | "job" | "health";

export type NormalizedClientError = {
  code: string;
  message: string;
  httpStatus?: number;
  source: ClientErrorSource;
};
