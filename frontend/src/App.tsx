import { AlertCircle, RotateCcw, Send, Server, SlidersHorizontal } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { createGatewayApi } from "./api/gateway";
import { OhmaticLogo } from "./components/OhmaticLogo";
import { ResultPanels } from "./components/ResultPanels";
import { SchematicSvg } from "./components/SchematicSvg";
import { StageRail } from "./components/StageRail";
import { useGenerateJob } from "./features/generate/useGenerateJob";
import { humanizeStage } from "./lib/format";
import type { GenerateOptions, Supplier } from "./types/api";

const examples = [
  "555 timer astable oscillator, 1 Hz LED blink, 5 V supply",
  "Passive RC low-pass filter, 1 kHz cutoff, 0603 passives",
  "NPN low-side relay driver with base resistor and flyback diode"
];

const defaultOptions: Required<GenerateOptions> = {
  temperature: 0.4,
  max_retries: 1,
  supplier: "local",
  max_components: 30
};

export default function App() {
  const job = useGenerateJob();
  const [prompt, setPrompt] = useState(examples[0]);
  const [temperature, setTemperature] = useState(defaultOptions.temperature);
  const [maxComponents, setMaxComponents] = useState(defaultOptions.max_components);
  const [supplier, setSupplier] = useState<Supplier>(defaultOptions.supplier);
  const [health, setHealth] = useState<"checking" | "ok" | "offline">("checking");

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
      temperature,
      max_retries: defaultOptions.max_retries,
      supplier,
      max_components: maxComponents
    });
  }

  const statusText = statusLabel(job.phase, job.stage);

  return (
    <main className="app-shell">
      <a className="skip-link" href="#prompt">
        Skip to prompt
      </a>
      <header className="app-header">
        <h1 className="sr-only">Ohmatic</h1>
        <nav className="top-nav" aria-label="Primary">
          <a href="#prompt">Input</a>
          <a href="#schematic-heading">Circuit</a>
          <a href="#inspector-heading">Output</a>
        </nav>
        <div className={`health-pill is-${health}`} role="status" aria-live="polite">
          <Server size={16} aria-hidden="true" />
          Gateway {health}
        </div>
      </header>

      <section className="hero-workbench" aria-label="Circuit generation workspace">
        <p className="version-badge">Version 1.0</p>
        <div className="hero-logo">
          <OhmaticLogo stage={job.stage} active={job.isBusy} />
        </div>

        <div className="hero-copy">
          <p className="kicker">Describe. Generate. Review.</p>
          <p>Turn circuit intent into a checked schematic, parts list, and JSON contract.</p>
          <p>The first visible circuit is the verified one.</p>
        </div>

      </section>

      <form className="prompt-panel command-dock" onSubmit={handleSubmit}>
        <div className="command-heading">
          <div>
            <span className="console-label">Gateway command</span>
            <h2>What should the circuit do?</h2>
          </div>
          <SlidersHorizontal size={20} aria-hidden="true" />
        </div>

        <label htmlFor="prompt">Circuit intent</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={6}
          placeholder="Example: 555 timer astable oscillator, 1 Hz LED blink, 5 V supply"
          disabled={job.isBusy}
        />

        <div className="command-grid">
          <fieldset>
            <legend>Generation options</legend>
            <label htmlFor="temperature">
              Temperature <span>{temperature.toFixed(1)}</span>
            </label>
            <input
              id="temperature"
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={temperature}
              onChange={(event) => setTemperature(Number(event.target.value))}
              disabled={job.isBusy}
            />

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

            <label htmlFor="supplier">Supplier</label>
            <select
              id="supplier"
              value={supplier}
              onChange={(event) => setSupplier(event.target.value as Supplier)}
              disabled={job.isBusy}
            >
              <option value="local">Local</option>
              <option value="octopart">Octopart</option>
            </select>
          </fieldset>

          <div className="example-list" aria-label="Example prompts">
            <span className="console-label">Reference prompts</span>
            {examples.map((example) => (
              <button key={example} type="button" onClick={() => setPrompt(example)} disabled={job.isBusy}>
                {example}
              </button>
            ))}
          </div>
        </div>

        <div className="form-actions">
          <button className="primary-button" type="submit" disabled={!prompt.trim() || job.isBusy}>
            <Send size={17} aria-hidden="true" />
            {job.isBusy ? "Generating" : "Generate"}
          </button>
          <button className="secondary-button" type="button" onClick={job.reset} disabled={job.phase === "idle"}>
            <RotateCcw size={17} aria-hidden="true" />
            Reset
          </button>
        </div>
      </form>

      <section className="workspace" aria-label="Circuit result workspace">
        <section className="main-panel" aria-labelledby="schematic-heading">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Circuit artifact</p>
              <h2 id="schematic-heading">{job.result?.circuit.metadata.title ?? "No circuit generated yet"}</h2>
            </div>
            <output className={`status-output is-${job.phase}`} aria-live="polite">
              {statusText}
            </output>
          </div>

          <StageRail stage={job.stage} phase={job.phase} />

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
            <SchematicSvg circuit={job.result?.circuit ?? null} />
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
              <dd>{job.result?.bom.length || job.result?.circuit.components.length || 0}</dd>
            </div>
          </dl>
        </section>

        <ResultPanels result={job.result} />
      </section>
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
