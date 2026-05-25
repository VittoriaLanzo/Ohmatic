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

export type GenerateJobState = {
  phase: "idle" | "submitting" | "polling" | "done" | "error";
  jobId: string | null;
  pollUrl: string | null;
  status: JobStatusResponse | null;
  stage: JobStage | null;
  result: GenerateResult | null;
  error: NormalizedClientError | null;
};

const initialState: GenerateJobState = {
  phase: "idle",
  jobId: null,
  pollUrl: null,
  status: null,
  stage: null,
  result: null,
  error: null
};

export function useGenerateJob(api: GatewayApi = createGatewayApi()) {
  const [state, setState] = useState<GenerateJobState>(initialState);
  const activeRun = useRef(0);

  useEffect(() => {
    return () => {
      activeRun.current += 1;
    };
  }, []);

  const reset = useCallback(() => {
    activeRun.current += 1;
    setState(initialState);
  }, []);

  const submit = useCallback(
    async (prompt: string, options: Required<GenerateOptions>) => {
      // PROMPT OUTPUT ENTRY: user text becomes POST /v1/generate here.
      // Returned job_id/poll_url drives all downstream surfaces:
      // StageRail pipeline state, SchematicSvg circuit artifact, ResultPanels checks/BOM/JSON.
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
  setState: Dispatch<SetStateAction<GenerateJobState>>
) {
  // PIPELINE ENTRY: every poll response updates the visible pipeline state.
  // Terminal "done" is where result.circuit, result.drc_warnings, result.bom,
  // and result.latency_ms enter the UI.
  while (activeRun.current === runId) {
    const status = await api.getJobStatus(pollUrl);
    if (activeRun.current !== runId) {
      return;
    }

    if (status.status === "done") {
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
