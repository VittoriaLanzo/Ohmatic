import { describe, expect, it, vi } from "vitest";
import { GatewayClientError, GatewayHttpClient, normalizeHttpError } from "./client";
import { HttpGatewayApi } from "./gateway";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

describe("GatewayHttpClient", () => {
  it("submits generation requests to the gateway contract endpoint", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ job_id: "job-1", poll_url: "/v1/jobs/job-1/status" }, { status: 202 })
    ) as unknown as typeof fetch;
    const api = new HttpGatewayApi(new GatewayHttpClient({ fetchImpl }));

    await expect(
      api.createGeneration({
        prompt: "555 timer blinking LED",
        options: { temperature: 0.4, max_retries: 1, supplier: "local", max_components: 30 }
      })
    ).resolves.toEqual({ job_id: "job-1", poll_url: "/v1/jobs/job-1/status" });

    expect(fetchImpl).toHaveBeenCalledWith(
      "/v1/generate",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("555 timer blinking LED")
      })
    );
  });

  it("polls a preserved gateway-relative poll URL", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ status: "running", stage: "drc", result: null, error: null }, { status: 200 })
    ) as unknown as typeof fetch;
    const api = new HttpGatewayApi(new GatewayHttpClient({ fetchImpl }));

    await expect(api.getJobStatus("/v1/jobs/job-1/status")).resolves.toMatchObject({
      status: "running",
      stage: "drc"
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/v1/jobs/job-1/status",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("normalizes flat gateway errors", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ error: "prompt must not be empty" }, { status: 400 })
    ) as unknown as typeof fetch;
    const api = new HttpGatewayApi(new GatewayHttpClient({ fetchImpl }));

    await expect(api.createGeneration({ prompt: "" })).rejects.toMatchObject({
      detail: {
        code: "http_400",
        message: "prompt must not be empty",
        httpStatus: 400,
        source: "submit"
      }
    });
  });

  it("normalizes async failed jobs", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(
        {
          status: "failed",
          stage: null,
          result: null,
          error: {
            code: "tier1_validation_failed",
            message: "Component IDs are not unique"
          }
        },
        { status: 200 }
      )
    ) as unknown as typeof fetch;
    const api = new HttpGatewayApi(new GatewayHttpClient({ fetchImpl }));

    await expect(api.getJobStatus("job-1")).rejects.toMatchObject({
      detail: {
        code: "tier1_validation_failed",
        message: "Component IDs are not unique",
        source: "job"
      }
    });
  });

  it("treats legacy error statuses as terminal failures", async () => {
    // A pre-fix gateway reports terminal failure as "error"; polling it as
    // still-running showed "queued" forever.
    const fetchImpl = vi.fn(async () =>
      jsonResponse(
        {
          status: "error",
          stage: null,
          result: null,
          error: { code: "pipeline_error", message: "boom" }
        },
        { status: 200 }
      )
    ) as unknown as typeof fetch;
    const api = new HttpGatewayApi(new GatewayHttpClient({ fetchImpl }));

    await expect(api.getJobStatus("job-1")).rejects.toMatchObject({
      detail: { code: "pipeline_error", message: "boom", source: "job" }
    });
  });

  it("maps flat 503 failures to inference_unavailable", () => {
    expect(normalizeHttpError(503, { error: "inference service unavailable" }, "submit")).toEqual({
      code: "inference_unavailable",
      message: "inference service unavailable",
      httpStatus: 503,
      source: "submit"
    });
  });

  it("preserves code-like 404 flat errors", () => {
    expect(normalizeHttpError(404, { error: "job_not_found" }, "poll")).toEqual({
      code: "job_not_found",
      message: "job_not_found",
      httpStatus: 404,
      source: "poll"
    });
  });

  it("attaches bearer auth only when configured", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ status: "ok" }, { status: 200 }));
    const api = new HttpGatewayApi(
      new GatewayHttpClient({ apiKey: "sk-ohm-test", fetchImpl: fetchMock as unknown as typeof fetch })
    );

    await api.checkHealth();

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer sk-ohm-test");
  });

  it("throws GatewayClientError instances", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ error: "job_not_found" }, { status: 404 })) as unknown as typeof fetch;
    const api = new HttpGatewayApi(new GatewayHttpClient({ fetchImpl }));

    await expect(api.getJobStatus("missing")).rejects.toBeInstanceOf(GatewayClientError);
  });
});
