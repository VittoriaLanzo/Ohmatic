import { useCallback, useRef, useState } from "react";
import type { GenerateOptions, GenerateResult, JobStage } from "../../types/api";

/**
 * In-browser generation over WebGPU (WebLLM), same job interface as
 * useGenerateJob so the App swaps engines transparently.
 *
 * THE KILLSWITCH SURVIVES THE BROWSER MOVE: generation runs on the user's GPU,
 * but every candidate is verified by the local gateway's POST /v1/verify -
 * the SAME analyze_schematic + feedback format as training/prod/benchmark.
 * No unverified circuit is ever delivered; retries use the trained feedback.
 *
 * Model: an MLC-compiled build of Ohmatic-Qwen3-8B (q4f16). Until the public
 * MLC artifact ships, the model id is configurable via
 * localStorage["ohmatic.webllmModel"].
 */

const DEFAULT_MODEL = "Qwen3-8B-q4f16_1-MLC"; // swap to VittoriaLanzo/Ohmatic-Qwen3-8B-q4f16_1-MLC at launch
const MAX_RETRIES = 3;

type Phase = "idle" | "submitting" | "polling" | "done" | "error";

type EngineState = {
  phase: Phase;
  stage: JobStage | null;
  jobId: string | null;
  result: GenerateResult | null;
  error: { code: string; message: string } | null;
  loadProgress: string;
};

const initial: EngineState = {
  phase: "idle", stage: null, jobId: null, result: null, error: null, loadProgress: ""
};

export function useBrowserEngine() {
  const [state, setState] = useState<EngineState>(initial);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const engineRef = useRef<any>(null);

  const reset = useCallback(() => setState(initial), []);

  const submit = useCallback(async (prompt: string, _options?: GenerateOptions) => {
    setState({ ...initial, phase: "submitting", loadProgress: "Loading model…" });
    const t0 = performance.now();
    try {
      // 1. Engine (cached across runs; WebLLM caches weights in IndexedDB)
      if (!engineRef.current) {
        const { CreateMLCEngine } = await import("@mlc-ai/web-llm");
        const modelId = localStorage.getItem("ohmatic.webllmModel") ?? DEFAULT_MODEL;
        engineRef.current = await CreateMLCEngine(modelId, {
          initProgressCallback: (p: { text: string }) =>
            setState((s) => ({ ...s, loadProgress: p.text }))
        });
      }
      const engine = engineRef.current;

      // 2. The byte-identical trained system prompt, from the single source
      const sp = await fetch("/v1/system-prompt").then((r) => r.json());
      const messages: { role: "system" | "user" | "assistant"; content: string }[] = [
        { role: "system", content: sp.system_prompt },
        { role: "user", content: prompt }
      ];

      // 3. Generate -> verify -> feedback loop (killswitch semantics)
      setState((s) => ({ ...s, phase: "polling", stage: "inference" }));
      let lastDiags: unknown[] = [];
      const tInferStart = performance.now();
      for (let attempt = 1; attempt <= MAX_RETRIES + 1; attempt++) {
        const reply = await engine.chat.completions.create({
          messages, temperature: 0, max_tokens: 2560
        });
        const raw: string = reply.choices[0]?.message?.content ?? "";
        const circuit = extractCircuit(raw);
        if (!circuit) {
          messages.push({ role: "assistant", content: raw });
          messages.push({ role: "user", content: "The output above is not valid JSON. Return ONLY a valid JSON object - no prose, no markdown fences." });
          continue;
        }
        setState((s) => ({ ...s, stage: "drc" }));
        const verdict = await fetch("/v1/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ circuit })
        }).then((r) => r.json());
        if (verdict.passed) {
          const tDone = performance.now();
          setState((s) => ({
            ...s,
            phase: "done",
            stage: null,
            jobId: `browser-${Date.now().toString(36)}`,
            result: {
              circuit: toUiCircuit(circuit),
              drc_warnings: [],
              latency_ms: {
                inference: Math.round(tDone - tInferStart),
                drc: 0
              }
            } as GenerateResult
          }));
          return;
        }
        lastDiags = verdict.diagnostics ?? [];
        if (attempt > MAX_RETRIES) break;
        setState((s) => ({ ...s, stage: "inference" }));
        messages.push({ role: "assistant", content: raw });
        messages.push({ role: "user", content: verdict.feedback });
      }
      // KILLSWITCH: retries exhausted - refuse, ask to clarify. Never deliver.
      setState((s) => ({
        ...s,
        phase: "error",
        stage: null,
        error: {
          code: "blocked_by_verification",
          message:
            `I generated several candidate designs on your GPU, but none passed ` +
            `electrical verification (${lastDiags.length} open findings) - and I don't ` +
            `deliver circuits I can't verify. Could you clarify the requirements? ` +
            `Supply voltage, key components, and intended behavior help most.`
        }
      }));
    } catch (err) {
      setState((s) => ({
        ...s,
        phase: "error",
        stage: null,
        error: {
          code: "browser_engine_error",
          message: err instanceof Error ? err.message : String(err)
        }
      }));
    } finally {
      void t0;
    }
  }, []);

  return {
    ...state,
    submit,
    reset,
    isBusy: state.phase === "submitting" || state.phase === "polling"
  };
}

/** Shared lenient extractor (mirror of the benchmark's): fences, first balanced object. */
function extractCircuit(text: string): Record<string, unknown> | null {
  let t = (text || "").trim();
  const fence = /```(?:json)?\s*([\s\S]*?)```/.exec(t);
  if (fence) t = fence[1].trim();
  try {
    const obj = JSON.parse(t);
    if (obj && typeof obj === "object" && !Array.isArray(obj)) return obj;
  } catch { /* fall through */ }
  let start = t.indexOf("{");
  while (start !== -1) {
    let depth = 0;
    for (let i = start; i < t.length; i++) {
      if (t[i] === "{") depth++;
      else if (t[i] === "}") {
        depth--;
        if (depth === 0) {
          try {
            const obj = JSON.parse(t.slice(start, i + 1));
            if (obj && typeof obj === "object") return obj as Record<string, unknown>;
          } catch { /* try next */ }
          break;
        }
      }
    }
    start = t.indexOf("{", start + 1);
  }
  return null;
}

/** Two-stage circuit JSON -> the flat shape the UI components expect. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function toUiCircuit(c: any): any {
  const topo = c.STAGE_1_TOPOLOGY ?? c;
  const layout = c.STAGE_2_LAYOUT ?? {};
  const pos: Record<string, { x: number; y: number }> = {};
  for (const n of layout.spatial_nodes ?? []) pos[n.id] = { x: n.x ?? 0, y: n.y ?? 0 };
  return {
    metadata: c.metadata ?? { title: "Untitled", description: "", version: "0.1", tags: [] },
    components: (topo.components ?? []).map((comp: any) => ({
      ...comp, x: pos[comp.id]?.x ?? 0, y: pos[comp.id]?.y ?? 0
    })),
    nets: topo.nets ?? []
  };
}
