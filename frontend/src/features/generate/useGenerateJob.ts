import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";
import { createGatewayApi, type GatewayApi } from "../../api/gateway";
import { GatewayClientError } from "../../api/client";
import type {
  GenerateOptions,
  GenerateRequest,
  GenerateResult,
  JobStage,
  JobStatusResponse,
  NormalizedClientError
} from "../../types/api";

const POLL_INTERVAL_MS = 500;
// A CPU generation runs for many minutes; one dropped poll must not orphan it.
// ~10 consecutive failures with backoff is ~20s of gateway outage tolerated.
const MAX_TRANSIENT_POLL_FAILURES = 10;
// Survives a page reload (same tab) so an in-flight generation is re-attached
// instead of orphaned behind the gateway's job lock.
const ACTIVE_JOB_KEY = "ohmatic.active-job";

export type GenerateJobState = {
  phase: "idle" | "submitting" | "polling" | "done" | "error";
  jobId: string | null;
  pollUrl: string | null;
  status: JobStatusResponse | null;
  stage: JobStage | null;
  progress: number | null;
  loops: number;
  etaS: number | null;
  elapsedS: number | null;
  result: GenerateResult | null;
  error: NormalizedClientError | null;
};

const initialState: GenerateJobState = {
  phase: "idle",
  jobId: null,
  pollUrl: null,
  status: null,
  stage: null,
  progress: null,
  loops: 0,
  etaS: null,
  elapsedS: null,
  result: null,
  error: null
};

type StoredJob = { jobId: string; pollUrl: string };

function readActiveJob(): StoredJob | null {
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_JOB_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<StoredJob>;
    return typeof parsed.jobId === "string" && typeof parsed.pollUrl === "string"
      ? { jobId: parsed.jobId, pollUrl: parsed.pollUrl }
      : null;
  } catch {
    return null;
  }
}

function saveActiveJob(job: StoredJob) {
  try {
    window.sessionStorage.setItem(ACTIVE_JOB_KEY, JSON.stringify(job));
  } catch {
    // storage unavailable: reload re-attach is best-effort
  }
}

function clearActiveJob() {
  try {
    window.sessionStorage.removeItem(ACTIVE_JOB_KEY);
  } catch {
    // ignore
  }
}

export function useGenerateJob(api: GatewayApi = createGatewayApi()) {
  const [state, setState] = useState<GenerateJobState>(initialState);
  const activeRun = useRef(0);

  useEffect(() => {
    return () => {
      activeRun.current += 1;
    };
  }, []);

  // Re-attach after a reload: the gateway still owns the job (and its result),
  // so the page picks the run back up instead of looking idle while the model
  // keeps the job lock for minutes.
  useEffect(() => {
    const stored = readActiveJob();
    if (!stored) {
      return;
    }
    const runId = activeRun.current + 1;
    activeRun.current = runId;
    setState({
      ...initialState,
      phase: "polling",
      jobId: stored.jobId,
      pollUrl: stored.pollUrl
    });
    void pollUntilTerminal(api, stored.pollUrl, runId, activeRun, setState, {
      silentlyDropLostJob: true
    }).catch(() => {
      if (activeRun.current === runId) {
        setState(initialState);
      }
    });
    // mount-only by design; api is stable for the app's lifetime
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reset = useCallback(() => {
    activeRun.current += 1;
    clearActiveJob();
    setState(initialState);
  }, []);

  const submit = useCallback(
    async (prompt: string, options: GenerateOptions) => {
      // PROMPT OUTPUT ENTRY: user text becomes POST /v1/generate here; the returned
      // job_id/poll_url drives StageRail, SchematicSvg, and ResultPanels.
      const runId = activeRun.current + 1;
      activeRun.current = runId;

      const request: GenerateRequest = {
        prompt,
        options
      };

      setState({
        ...initialState,
        phase: "submitting"
      });

      try {
        const accepted = await api.createGeneration(request);
        if (activeRun.current !== runId) {
          return;
        }

        saveActiveJob({ jobId: accepted.job_id, pollUrl: accepted.poll_url });
        setState({
          ...initialState,
          phase: "polling",
          jobId: accepted.job_id,
          pollUrl: accepted.poll_url
        });

        await pollUntilTerminal(api, accepted.poll_url, runId, activeRun, setState);
      } catch (error) {
        if (activeRun.current !== runId) {
          return;
        }
        clearActiveJob();
        setState((current) => ({
          ...current,
          phase: "error",
          error: normalizeThrownError(error)
        }));
      }
    },
    [api]
  );

  return {
    ...state,
    submit,
    reset,
    isBusy: state.phase === "submitting" || state.phase === "polling"
  };
}

async function pollUntilTerminal(
  api: GatewayApi,
  pollUrl: string,
  runId: number,
  activeRun: MutableRefObject<number>,
  setState: Dispatch<SetStateAction<GenerateJobState>>,
  opts: { silentlyDropLostJob?: boolean } = {}
) {
  // PIPELINE ENTRY: every poll updates the visible pipeline state; terminal "done"
  // is where result.circuit, drc_warnings, bom, and latency_ms enter the UI.
  let transientFailures = 0;
  while (activeRun.current === runId) {
    let status: JobStatusResponse;
    try {
      status = await api.getJobStatus(pollUrl);
      transientFailures = 0;
    } catch (error) {
      if (activeRun.current !== runId) {
        return;
      }
      const detail = error instanceof GatewayClientError ? error.detail : null;

      if (detail?.source === "job") {
        // The job itself ended in failure (killswitch refusal, pipeline error).
        clearActiveJob();
        setState((current) => ({
          ...current,
          phase: "error",
          result: null,
          error: detail
        }));
        return;
      }

      if (detail?.httpStatus === 404) {
        // The gateway no longer knows the job: it restarted and lost its store.
        clearActiveJob();
        if (opts.silentlyDropLostJob) {
          setState(initialState);
          return;
        }
        setState((current) => ({
          ...current,
          phase: "error",
          error: {
            code: "job_lost",
            message: "The gateway restarted and lost this generation. Generate again.",
            source: "poll"
          }
        }));
        return;
      }

      // Transient transport failure (proxy hiccup, busy gateway): keep the run
      // alive instead of orphaning a generation that is still computing.
      transientFailures += 1;
      if (transientFailures >= MAX_TRANSIENT_POLL_FAILURES) {
        clearActiveJob();
        setState((current) => ({
          ...current,
          phase: "error",
          error: normalizeThrownError(error)
        }));
        return;
      }
      await delay(POLL_INTERVAL_MS * Math.min(transientFailures, 6));
      continue;
    }

    if (activeRun.current !== runId) {
      return;
    }

    if (status.status === "done") {
      clearActiveJob();
      setState((current) => ({
        ...current,
        phase: "done",
        status,
        stage: null,
        result: status.result,
        error: null
      }));
      return;
    }

    if (status.status === "failed") {
      clearActiveJob();
      setState((current) => ({
        ...current,
        phase: "error",
        status,
        stage: current.stage,
        result: null,
        error: {
          code: status.error.code,
          message: status.error.message,
          source: "job"
        }
      }));
      return;
    }

    setState((current) => ({
      ...current,
      phase: "polling",
      status,
      stage: status.stage,
      progress: "progress" in status ? ((status as { progress?: number | null }).progress ?? null) : null,
      loops: "loops" in status ? ((status as { loops?: number }).loops ?? 0) : 0,
      etaS: (status as { eta_s?: number | null }).eta_s ?? null,
      elapsedS: (status as { elapsed_s?: number | null }).elapsed_s ?? null,
      error: null
    }));

    await delay(POLL_INTERVAL_MS);
  }
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function normalizeThrownError(error: unknown): NormalizedClientError {
  if (error instanceof GatewayClientError) {
    return error.detail;
  }
  if (error instanceof Error) {
    return {
      code: "client_error",
      message: error.message,
      source: "poll"
    };
  }
  return {
    code: "unknown_error",
    message: "Unknown frontend error",
    source: "poll"
  };
}
