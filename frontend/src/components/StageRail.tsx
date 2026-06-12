import { useRef } from "react";
import type { CSSProperties } from "react";
import type { JobStage } from "../types/api";

type StageRailProps = {
  stage: JobStage | null;
  phase: "idle" | "submitting" | "polling" | "done" | "error";
  progress?: number | null;
  loops?: number;
  etaS?: number | null;
  elapsedS?: number | null;
};

function fmt(s: number): string {
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

// PIPELINE UI ENTRY: stations are the REAL pipeline stages reported by the
// gateway (t5 / generate / verify). The correction loop is the return bus
// from Verify back to Generate; its counter is the number of loopbacks.
const STATIONS = [
  { id: "t5", label: "Normalize", x: 60, target: 0.16 },
  { id: "generate", label: "Generate", x: 380, target: 0.55 },
  { id: "verify", label: "Verify", x: 700, target: 0.86 },
  { id: "done", label: "Deliver", x: 952, target: 1 }
] as const;

const TRACE = "M60 26 H180 L210 12 H300 L330 26 H540 L570 40 H650 L680 26 H850 L880 12 H922 L952 26";
// Return bus: Verify back to Generate, routed below the main trace.
const LOOP = "M700 34 V58 H380 V34";

const STAGE_INDEX: Record<string, number> = {
  queued: 0, t5: 0, inference: 1, generate: 1, drc: 2, verify: 2, bom: 2
};

export function StageRail({ stage, phase, progress, loops = 0, etaS = null, elapsedS = null }: StageRailProps) {
  const index = phase === "done" ? 3 : STAGE_INDEX[stage ?? "queued"] ?? 0;
  const busy = phase === "submitting" || phase === "polling";
  const real = typeof progress === "number" && progress > 0 ? progress : null;
  // Token progress fills the Generate span. Pre-token Generate creeps only to
  // 0.21 (just past its pad) so the token formula takes over seamlessly; a
  // high-water guard makes the bar physically unable to move backward within
  // a run - the old 0.55 creep vs 0.18+real handoff snapped the bar back to
  // the start and read as a reset to queued.
  const computed = phase === "done" ? 1
    : phase === "idle" ? 0
    : index === 1 && real !== null ? 0.18 + real * 0.37
    : index === 1 ? 0.21
    : STATIONS[index].target;
  const high = useRef(0);
  if (phase === "idle") high.current = 0;
  const lit = Math.max(computed, phase === "idle" ? 0 : high.current);
  high.current = lit;
  const seconds = phase === "done" ? 1.4 : index === 1 && real !== null ? 0.55 : busy ? 9 : 0.4;
  const looping = busy && loops > 0;

  return (
    <div
      className={`stage-trace is-${phase} ${looping ? "is-looping" : ""}`}
      style={{ "--lit": lit, "--creep": `${seconds}s` } as CSSProperties}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(lit * 100)}
      aria-label="Generation pipeline"
    >
      <svg viewBox="0 0 1000 72" preserveAspectRatio="none" aria-hidden="true">
        <path className="stage-trace-base" d={TRACE} pathLength={1} />
        <path className="stage-loop-base" d={LOOP} pathLength={1} />
        <path className="stage-trace-lit" d={TRACE} pathLength={1} />
        <path className="stage-trace-glowhead" d={TRACE} pathLength={1} />
        <path className="stage-loop-lit" d={LOOP} pathLength={1} />
        {STATIONS.map((s, i) => (
          <g key={s.id} className={`stage-pad ${i <= index && phase !== "idle" ? "is-lit" : ""} ${i === index && busy ? "is-active" : ""}`}>
            <circle cx={s.x} cy={26} r={7} className="stage-pad-ring" />
            <circle cx={s.x} cy={26} r={3} className="stage-pad-core" />
          </g>
        ))}
      </svg>
      {loops > 0 && (
        <span className="stage-loop-count" title={`${loops} correction ${loops === 1 ? "pass" : "passes"} through the rule checker`}>
          ⟲ ×{loops}
        </span>
      )}
      {phase === "done" ? (
        <span className="stage-trace-pct">100%</span>
      ) : real !== null ? (
        <span className="stage-trace-pct">
          {(real * 100).toFixed(1)}%{etaS !== null ? ` · ~${fmt(etaS)} left` : ""}
        </span>
      ) : busy && elapsedS !== null ? (
        <span className="stage-trace-pct is-elapsed">
          {STATIONS[index].label.toLowerCase()}… {fmt(elapsedS)}
        </span>
      ) : null}
      <div className="stage-trace-labels" aria-hidden="true">
        {STATIONS.map((s, i) => (
          <span key={s.id} className={i <= index && phase !== "idle" ? "is-lit" : ""} style={{ left: `${s.x / 10}%` }}>
            {s.label}
          </span>
        ))}
      </div>
      <span className="sr-only" aria-live="polite">
        {phase === "idle" ? "Ready"
          : phase === "error" ? "Stopped"
          : busy && real === null && index <= 1 ? "Preparing: loading model and processing prompt"
          : STATIONS[index].label}
      </span>
    </div>
  );
}
