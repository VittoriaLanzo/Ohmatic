import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GatewayClientError } from "../../api/client";
import type { GatewayApi } from "../../api/gateway";
import type { GenerateResult, JobStatusResponse } from "../../types/api";
import { useGenerateJob } from "./useGenerateJob";

const ACTIVE_JOB_KEY = "ohmatic.active-job";

const generateResult: GenerateResult = {
  circuit: {
    metadata: { title: "RC low-pass", description: "", version: "0.1", tags: [] },
    components: [],
    nets: []
  },
  drc_warnings: [],
  latency_ms: { inference: 1, drc: 0 }
};

const runningStatus: JobStatusResponse = {
  status: "running",
  stage: "generate",
  result: null,
  error: null
};

const doneStatus: JobStatusResponse = {
  status: "done",
  stage: null,
  result: generateResult,
  error: null
};

function makeApi(getJobStatus: GatewayApi["getJobStatus"]): GatewayApi {
  return {
    createGeneration: vi.fn(async () => ({ job_id: "job-1", poll_url: "/v1/jobs/job-1/status" })),
    getJobStatus,
    checkHealth: vi.fn(async () => ({ status: "ok" as const }))
  };
}

afterEach(() => {
  window.sessionStorage.clear();
});

describe("useGenerateJob", () => {
  it("treats a failed job as terminal instead of polling forever", async () => {
    // The real api throws a source:"job" error for status "failed" AND legacy
    // "error" payloads; either must end the run, never show "queued".
    const api = makeApi(
      vi.fn(async () => {
        throw new GatewayClientError({
          code: "blocked_by_verification",
          message: "Could not verify this design.",
          source: "job"
        });
      })
    );
    const { result: hook } = renderHook(() => useGenerateJob(api));

    await act(async () => {
      await hook.current.submit("rc filter", {});
    });

    expect(hook.current.phase).toBe("error");
    expect(hook.current.error?.code).toBe("blocked_by_verification");
    expect(window.sessionStorage.getItem(ACTIVE_JOB_KEY)).toBeNull();
  });

  it("rides out transient poll failures while the model is computing", async () => {
    const getStatus = vi
      .fn<GatewayApi["getJobStatus"]>()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(runningStatus)
      .mockResolvedValue(doneStatus);
    const api = makeApi(getStatus);
    const { result: hook } = renderHook(() => useGenerateJob(api));

    await act(async () => {
      await hook.current.submit("rc filter", {});
    });

    expect(hook.current.phase).toBe("done");
    expect(hook.current.result).toEqual(generateResult);
    expect(getStatus.mock.calls.length).toBeGreaterThanOrEqual(3);
  }, 15000);

  it("stops with job_lost when the gateway forgot the job", async () => {
    const api = makeApi(
      vi.fn(async () => {
        throw new GatewayClientError({
          code: "job_not_found",
          message: "job_not_found",
          httpStatus: 404,
          source: "poll"
        });
      })
    );
    const { result: hook } = renderHook(() => useGenerateJob(api));

    await act(async () => {
      await hook.current.submit("rc filter", {});
    });

    expect(hook.current.phase).toBe("error");
    expect(hook.current.error?.code).toBe("job_lost");
  });

  it("re-attaches to a stored job after a reload", async () => {
    window.sessionStorage.setItem(
      ACTIVE_JOB_KEY,
      JSON.stringify({ jobId: "job-9", pollUrl: "/v1/jobs/job-9/status" })
    );
    const api = makeApi(vi.fn(async () => doneStatus));
    const { result: hook } = renderHook(() => useGenerateJob(api));

    await waitFor(() => expect(hook.current.phase).toBe("done"));
    expect(hook.current.jobId).toBe("job-9");
    expect(hook.current.result).toEqual(generateResult);
    expect(window.sessionStorage.getItem(ACTIVE_JOB_KEY)).toBeNull();
  });

  it("silently drops a stored job the gateway no longer knows", async () => {
    window.sessionStorage.setItem(
      ACTIVE_JOB_KEY,
      JSON.stringify({ jobId: "job-9", pollUrl: "/v1/jobs/job-9/status" })
    );
    const api = makeApi(
      vi.fn(async () => {
        throw new GatewayClientError({
          code: "job_not_found",
          message: "job_not_found",
          httpStatus: 404,
          source: "poll"
        });
      })
    );
    const { result: hook } = renderHook(() => useGenerateJob(api));

    await waitFor(() => expect(window.sessionStorage.getItem(ACTIVE_JOB_KEY)).toBeNull());
    expect(hook.current.phase).toBe("idle");
  });
});
