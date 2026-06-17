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
  /** True for a real component (a BOM line you source); false for a schematic
   *  power/ground rail symbol, which is notation, not a purchasable part. */
  is_part: boolean;
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
  eta_s?: number | null;
  elapsed_s?: number | null;
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

export type ClientErrorSource = "submit" | "poll" | "job" | "health" | "procurement";

export type ProcurementLinkAction = {
  type: string;
  part_id: string;
  supplier: string;
  quantity: number;
  url: string;
  label: string;
  disclosure?: string;
};

export type ProcurementResponse = {
  procurement_status: string;
  link_actions: ProcurementLinkAction[];
  eligibility_disclosures: string[];
  supplier?: string;
};

export type ProcurementRequest = {
  parts_list: PartsListRow[];
  supplier?: string;
  quantity?: number;
};

export type NormalizedClientError = {
  code: string;
  message: string;
  httpStatus?: number;
  source: ClientErrorSource;
};
