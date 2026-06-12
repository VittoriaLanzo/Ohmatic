import { AlertCircle, Maximize2, RotateCcw, Send, Server, SlidersHorizontal, ZoomIn, ZoomOut } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { createGatewayApi } from "./api/gateway";
import { HardwareBadge } from "./components/HardwareBadge";
import { OhmaticLogo } from "./components/OhmaticLogo";
import { ResultPanels } from "./components/ResultPanels";
import { SchematicSvg } from "./components/SchematicSvg";
import { StageRail } from "./components/StageRail";
import { useBrowserEngine } from "./features/generate/useBrowserEngine";
import { useGenerateJob } from "./features/generate/useGenerateJob";
import { humanizeStage } from "./lib/format";
import type { GenerateOptions } from "./types/api";
import type { SymbolStyle } from "./components/schematic/symbols";

const examples = [
  "555 timer astable oscillator, 1 Hz LED blink, 5 V supply",
  "Passive RC low-pass filter, 1 kHz cutoff, 0603 passives",
  "NPN low-side relay driver with base resistor and flyback diode"
];

const defaultOptions: Required<Pick<GenerateOptions, "max_retries" | "max_components">> = {
  max_retries: 1,
  max_components: 30
};

type CompletionMotion = "idle" | "burst" | "returning" | "settled";

export default function App() {
  const gatewayJob = useGenerateJob();
  const browserJob = useBrowserEngine();
  const [engineMode, setEngineMode] = useState<"gateway" | "browser">("gateway");
  const [browserCapable, setBrowserCapable] = useState(false);
  const job = engineMode === "browser" ? browserJob : gatewayJob;
  const [prompt, setPrompt] = useState(examples[0]);
  const [maxComponents, setMaxComponents] = useState(defaultOptions.max_components);
  const [symbolStyle, setSymbolStyle] = useState<SymbolStyle>("ansi");
  const [schematicZoom, setSchematicZoom] = useState(1);
  const [health, setHealth] = useState<"checking" | "ok" | "offline">("checking");
  const [completionMotion, setCompletionMotion] = useState<CompletionMotion>("idle");

  useEffect(() => {
    const nav = navigator as Navigator & { gpu?: { requestAdapter(): Promise<unknown | null> } };
    if (!nav.gpu) return;
    void Promise.all([
      nav.gpu.requestAdapter().catch(() => null),
      fetch("/v1/doctor").then((r) => (r.ok ? r.json() : null)).catch(() => null)
    ]).then(([adapter, doctor]) => {
      setBrowserCapable(Boolean(adapter) && (doctor?.vram_mb ?? 0) >= 6000);
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void jobCheckHealth().then((status) => {
      if (!cancelled) {
        setHealth(status);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (job.phase !== "done") {
      setCompletionMotion("idle");
      return;
    }

    setCompletionMotion("burst");
    const returnTimer = window.setTimeout(() => {
      setCompletionMotion("returning");
    }, 260);
    const settleTimer = window.setTimeout(() => {
      setCompletionMotion("settled");
    }, 1900);

    return () => {
      window.clearTimeout(returnTimer);
      window.clearTimeout(settleTimer);
    };
  }, [job.phase, job.jobId]);

  async function jobCheckHealth() {
    try {
      const api = createGatewayApi();
      const response = await api.checkHealth();
      return response.status === "ok" ? "ok" : "offline";
    } catch {
      return "offline";
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!prompt.trim() || job.isBusy) {
      return;
    }

    await job.submit(prompt.trim(), {
      max_retries: defaultOptions.max_retries,
      max_components: maxComponents
    });
  }

  const statusText = statusLabel(job.phase, job.stage);
  const isReturningToStart = job.phase === "done" && completionMotion === "returning";
  const isSettledDone = job.phase === "done" && completionMotion === "settled";
  const visualPhase = isReturningToStart || isSettledDone ? "idle" : job.phase;
  const visualStage = isReturningToStart || isSettledDone ? null : job.stage;
  const motionPhase = visualPhase === "polling" && visualStage ? visualStage : visualPhase;
  const stageKey = visualStage ?? visualPhase;
  const logoReturning = job.phase === "done" && completionMotion !== "settled";
  const logoPhase = logoReturning ? "idle" : visualPhase;
  const logoStage = logoReturning ? null : visualStage;

  return (
    <main className={`app-shell motion-${motionPhase}`} data-motion-phase={motionPhase} data-stage={stageKey}>
      <a className="skip-link" href="#prompt">
        Skip to prompt
      </a>
      <div className="pcb-backplane" aria-hidden="true">
        <span className="pcb-backplane__grid" />
        <span className="pcb-backplane__lane pcb-backplane__lane--primary" />
        <span className="pcb-backplane__lane pcb-backplane__lane--secondary" />
        <span className="pcb-backplane__node pcb-backplane__node--a" />
        <span className="pcb-backplane__node pcb-backplane__node--b" />
        <span className="pcb-backplane__node pcb-backplane__node--c" />
      </div>
      <header className="app-header">
        <h1 className="sr-only">Ohmatic</h1>
        <div className="header-logo" aria-hidden="true">
          <OhmaticLogo stage={logoStage} phase={logoPhase} active={job.isBusy} returning={logoReturning} />
        </div>
        <nav className="top-nav" aria-label="Primary">
          <a href="#prompt">Input</a>
          <a href="#schematic-heading">Circuit</a>
          <a href="#inspector-heading">Output</a>
        </nav>
        <span className="version-badge">v1.0</span>
        <div className={`health-pill is-${health}`} role="status" aria-live="polite">
          <Server size={16} aria-hidden="true" />
          Gateway {health}
        </div>
        <HardwareBadge />
      </header>

      <form className={`prompt-panel command-dock ${job.isBusy ? "is-transmitting" : ""}`} onSubmit={handleSubmit}>
        <div className="command-heading">
          <div>
            <span className="console-label">Describe. Generate. Review.</span>
            <h2>What should the circuit do?</h2>
          </div>
        </div>

        <label className="sr-only" htmlFor="prompt">Circuit intent</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={3}
          placeholder="Example: 555 timer astable oscillator, 1 Hz LED blink, 5 V supply"
          disabled={job.isBusy}
        />

        <div className="example-list" aria-label="Example prompts">
          {examples.map((example) => (
            <button key={example} type="button" onClick={() => setPrompt(example)} disabled={job.isBusy}>
              {example}
            </button>
          ))}
        </div>

        <div className="form-actions">
          <div className="segmented-control engine-toggle" role="group" aria-label="Inference engine">
            <button type="button" className={engineMode === "gateway" ? "is-selected" : ""}
              aria-pressed={engineMode === "gateway"} onClick={() => setEngineMode("gateway")} disabled={job.isBusy}>
              Gateway
            </button>
            <button type="button" className={engineMode === "browser" ? "is-selected" : ""}
              aria-pressed={engineMode === "browser"} onClick={() => setEngineMode("browser")}
              disabled={job.isBusy || !browserCapable}
              title={browserCapable
                ? "Runs the model on YOUR GPU via WebGPU; verification stays with the rule checker"
                : "Needs WebGPU + ~6 GB dedicated GPU memory; not available on this machine"}>
              In-browser
            </button>
          </div>
          <details className="options-disclosure">
            <summary>
              <SlidersHorizontal size={14} aria-hidden="true" />
              Options
            </summary>
            <div className="options-body">
              <label htmlFor="max-components">
                Max components <span>{maxComponents}</span>
              </label>
              <input
                id="max-components"
                type="number"
                min="1"
                max="120"
                value={maxComponents}
                onChange={(event) => setMaxComponents(Number(event.target.value))}
                disabled={job.isBusy}
              />
            </div>
          </details>
          <button className="primary-button" type="submit" disabled={!prompt.trim() || job.isBusy}>
            <Send size={17} aria-hidden="true" />
            {job.isBusy ? "Generating" : "Generate"}
          </button>
          <button className="secondary-button" type="button" onClick={job.reset} disabled={job.phase === "idle"}>
            <RotateCcw size={17} aria-hidden="true" />
            Reset
          </button>
        </div>
        {engineMode === "browser" && browserJob.loadProgress && browserJob.isBusy && (
          <p className="engine-progress" aria-live="polite">{browserJob.loadProgress}</p>
        )}
      </form>

      <section className="workspace" aria-label="Circuit result workspace">
        <section className="main-panel" aria-labelledby="schematic-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Workbench</p>
              <h2 id="schematic-heading">{job.result?.circuit.metadata.title ?? "No circuit generated yet"}</h2>
            </div>
            <output className={`status-output is-${job.phase}`} aria-live="polite">
              {statusText}
            </output>
          </div>

          <div className="schematic-toolbar" aria-label="Schematic controls">
            <div className="segmented-control" role="group" aria-label="Schematic symbol style">
              <button
                type="button"
                className={symbolStyle === "ansi" ? "is-selected" : ""}
                aria-pressed={symbolStyle === "ansi"}
                onClick={() => setSymbolStyle("ansi")}
              >
                ANSI
              </button>
              <button
                type="button"
                className={symbolStyle === "iec" ? "is-selected" : ""}
                aria-pressed={symbolStyle === "iec"}
                onClick={() => setSymbolStyle("iec")}
              >
                IEC
              </button>
            </div>
            <div className="schematic-zoom-controls" role="group" aria-label="Schematic zoom">
              <button type="button" aria-label="Fit schematic" title="Fit schematic" onClick={() => setSchematicZoom(1)}>
                <Maximize2 size={16} aria-hidden="true" />
              </button>
              <button
                type="button"
                aria-label="Zoom out"
                title="Zoom out"
                onClick={() => setSchematicZoom((current) => Math.max(0.75, Number((current - 0.15).toFixed(2))))}
              >
                <ZoomOut size={16} aria-hidden="true" />
              </button>
              <button
                type="button"
                aria-label="Zoom in"
                title="Zoom in"
                onClick={() => setSchematicZoom((current) => Math.min(1.6, Number((current + 0.15).toFixed(2))))}
              >
                <ZoomIn size={16} aria-hidden="true" />
              </button>
            </div>
          </div>

          <StageRail stage={visualStage} phase={visualPhase} />

          {job.error && (
            <div className="error-box" role="alert">
              <AlertCircle size={18} aria-hidden="true" />
              <div>
                <strong>{job.error.code}</strong>
                <p>{job.error.message}</p>
              </div>
            </div>
          )}

          <div className="schematic-frame">
            <SchematicSvg circuit={job.result?.circuit ?? null} phase={visualPhase} symbolStyle={symbolStyle} zoom={schematicZoom} />
          </div>

          <dl className="metadata-grid">
            <div>
              <dt>Check state</dt>
              <dd>{humanizeStage(job.stage)}</dd>
            </div>
            <div>
              <dt>Generation ID</dt>
              <dd>{job.jobId ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Symbols</dt>
              <dd>{job.result?.circuit.components.length ?? 0}</dd>
            </div>
            <div>
              <dt>Nets</dt>
              <dd>{job.result?.circuit.nets.length ?? 0}</dd>
            </div>
            <div>
              <dt>Warnings</dt>
              <dd>{job.result?.drc_warnings.length ?? 0}</dd>
            </div>
            <div>
              <dt>Parts</dt>
              <dd>{job.result?.parts_list?.length || job.result?.bom?.length || job.result?.circuit.components.length || 0}</dd>
            </div>
          </dl>
        </section>

        <ResultPanels result={job.result} phase={visualPhase} />
      </section>

      <footer className="board-footer">
        <a
          className="star-button"
          href="https://github.com/VittoriaLanzo/Ohmatic"
          target="_blank"
          rel="noreferrer"
        >
          <span aria-hidden="true">★</span> Star Ohmatic on GitHub
        </a>
        <span className="board-footer-note">Open source · FSL-1.1 licensed</span>
      </footer>
    </main>
  );
}

function statusLabel(phase: string, stage: string | null) {
  if (phase === "submitting") {
    return "Submitting";
  }
  if (phase === "polling") {
    return stage ? `Running ${humanizeStage(stage)}` : "Queued";
  }
  if (phase === "done") {
    return "Ready";
  }
  if (phase === "error") {
    return "Needs attention";
  }
  return "Ready";
}
