import { GatewayClientError, GatewayHttpClient, normalizeJobError } from "./client";
import { createMockGatewayApi } from "./mock";
import type {
  GenerateAcceptedResponse,
  GenerateRequest,
  HealthResponse,
  JobStatusResponse
} from "../types/api";

export interface GatewayApi {
  createGeneration(request: GenerateRequest): Promise<GenerateAcceptedResponse>;
  getJobStatus(jobIdOrPollUrl: string): Promise<JobStatusResponse>;
  checkHealth(): Promise<HealthResponse>;
}

export class HttpGatewayApi implements GatewayApi {
  constructor(private readonly client = new GatewayHttpClient()) {}

  // BACKEND ENTRY: prompt -> gateway.
  // Wire the real backend here. The browser must call only the gateway public API,
  // never inference/verifier/enricher directly.
  // Contract: POST /v1/generate returns 202 with { job_id, poll_url }.
  // Source of truth: shared/docs/contracts.md.
  createGeneration(request: GenerateRequest): Promise<GenerateAcceptedResponse> {
    return this.client.post<GenerateAcceptedResponse>("/v1/generate", request, "submit");
  }

  async getJobStatus(jobIdOrPollUrl: string): Promise<JobStatusResponse> {
    // BACKEND ENTRY: gateway job status.
    // Pipeline rendering starts from this response: pending/running/done/failed plus stage
    // values such as "inference", "drc", and "bom".
    // Prefer backend-provided poll_url so backend routing can evolve without UI rewrites.
    const path = jobIdOrPollUrl.startsWith("/")
      ? jobIdOrPollUrl
      : `/v1/jobs/${encodeURIComponent(jobIdOrPollUrl)}/status`;
    const status = await this.client.get<JobStatusResponse>(path, "poll");

    if (status.status === "failed") {
      throw new GatewayClientError(normalizeJobError(status.error));
    }

    return status;
  }

  // BACKEND ENTRY: gateway liveness probe. Keep /health unauthenticated in local and server mode.
  checkHealth(): Promise<HealthResponse> {
    return this.client.get<HealthResponse>("/health", "health");
  }
}

export function createGatewayApi(): GatewayApi {
  if (import.meta.env.VITE_OHMATIC_USE_MOCK === "1") {
    return createMockGatewayApi();
  }
  return new HttpGatewayApi();
}
