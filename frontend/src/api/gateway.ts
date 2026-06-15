import { GatewayClientError, GatewayHttpClient, normalizeJobError } from "./client";
import type {
  GenerateAcceptedResponse,
  GenerateRequest,
  HealthResponse,
  JobStatusResponse,
  ProcurementRequest,
  ProcurementResponse
} from "../types/api";

export interface GatewayApi {
  createGeneration(request: GenerateRequest): Promise<GenerateAcceptedResponse>;
  getJobStatus(jobIdOrPollUrl: string): Promise<JobStatusResponse>;
  checkHealth(): Promise<HealthResponse>;
  getProcurementMatches(request: ProcurementRequest): Promise<ProcurementResponse>;
}

export class HttpGatewayApi implements GatewayApi {
  constructor(private readonly client = new GatewayHttpClient()) {}

  // BACKEND ENTRY: prompt -> gateway. The browser must call ONLY the gateway public
  // API, never inference/verifier/enricher directly. Contract: POST /v1/generate
  // returns 202 with { job_id, poll_url } (source: shared/docs/contracts.md).
  createGeneration(request: GenerateRequest): Promise<GenerateAcceptedResponse> {
    return this.client.post<GenerateAcceptedResponse>("/v1/generate", request, "submit");
  }

  async getJobStatus(jobIdOrPollUrl: string): Promise<JobStatusResponse> {
    // BACKEND ENTRY: gateway job status. Pipeline rendering starts here
    // (pending/running/done/failed + stage). Prefer the backend poll_url so routing
    // can evolve without UI rewrites.
    const path = jobIdOrPollUrl.startsWith("/")
      ? jobIdOrPollUrl
      : `/v1/jobs/${encodeURIComponent(jobIdOrPollUrl)}/status`;
    const status = await this.client.get<JobStatusResponse>(path, "poll");

    // "failed" is the contract; "error" is what a pre-fix gateway emits. Both are
    // terminal - treating either as still-running polls a finished job forever.
    const raw = (status as { status: string }).status;
    if (raw === "failed" || raw === "error") {
      const failed = status as { error?: { code?: unknown; message?: unknown } | null };
      throw new GatewayClientError(normalizeJobError(failed.error ?? {}));
    }

    return status;
  }

  // BACKEND ENTRY: gateway liveness probe. Keep /health unauthenticated in local and server mode.
  checkHealth(): Promise<HealthResponse> {
    return this.client.get<HealthResponse>("/health", "health");
  }

  // BACKEND ENTRY: post-design procurement. The deterministic parts_list becomes disclosed
  // supplier link-outs (Jameco lookups stay credential-gated server-side). Contract:
  // POST /v1/procurement/matches (source: shared/procurement.py).
  getProcurementMatches(request: ProcurementRequest): Promise<ProcurementResponse> {
    return this.client.post<ProcurementResponse>("/v1/procurement/matches", request, "procurement");
  }
}

export function createGatewayApi(): GatewayApi {
  return new HttpGatewayApi();
}
