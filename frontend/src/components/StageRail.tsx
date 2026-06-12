import type { CSSProperties } from "react";
import type { JobStage } from "../types/api";

type StageRailProps = {
  stage: JobStage | null;
  phase: "idle" | "submitting" | "polling" | "done" | "error";
  progress?: number | null;
};

// PIPELINE UI ENTRY: maps backend job `stage` values from GET /v1/jobs/{id}/status
// to the trace. Add new backend stages here if the gateway contract grows.
//
// PCB trace of five pads; the lit portion creeps toward a target just short of the
// next pad while a stage runs, so it never sits still or jumps.
const STATIONS = [
  { id: "queued", label: "Queued", x: 36, target: 0.21 },
  { id: "inference", label: "Inference", x: 268, target: 0.45 },
  { id: "drc", label: "DRC", x: 500, target: 0.69 },
  { id: "bom", label: "BOM", x: 732, target: 0.93 },
  { id: "done", label: "Done", x: 964, target: 1 }
] as const;

// One routed trace with 45-degree jogs, pad to pad. pathLength is normalized
// to 1 so stroke-dashoffset maps directly to "fraction lit".
const TRACE = "M36 30 H120 L150 14 H230 L252 30 H384 L414 46 H470 L500 30 H616 L646 14 H702 L732 30 H848 L878 46 H934 L964 30";

export function StageRail({ stage, phase, progress }: StageRailProps) {
  const index = activeIndex(stage, phase);
  const busy = phase === "submitting" || phase === "polling";
  // Real token progress when the gateway reports it (fine-grained, monotonic);
  // the stage-target creep is the fallback for phases with no signal yet.
  const real = typeof progress === "number" && progress > 0 ? progress : null;
  const lit = phase === "done" ? 1
    : phase === "idle" ? 0
    : real !== null ? 0.06 + real * 0.93
    : STATIONS[index].target;
  // Short transition between 500ms polls keeps real progress smooth; long creep
  // covers the signal-less load phase; brisk completion.
  const seconds = phase === "done" ? 1.4 : real !== null ? 0.55 : busy ? 9 : 0.4;

  return (
    <div
      className={`stage-trace is-${phase}`}
      style={{ "--lit": lit, "--creep": `${seconds}s` } as CSSProperties}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(lit * 100)}
      aria-label="Generation pipeline"
    >
      <svg viewBox="0 0 1000 64" preserveAspectRatio="none" aria-hidden="true">
        <path className="stage-trace-base" d={TRACE} pathLength={1} />
        <path className="stage-trace-lit" d={TRACE} pathLength={1} />
        <path className="stage-trace-glowhead" d={TRACE} pathLength={1} />
        {STATIONS.map((s, i) => (
          <g key={s.id} className={`stage-pad ${i <= index && phase !== "idle" ? "is-lit" : ""} ${i === index && busy ? "is-active" : ""}`}>
            <circle cx={s.x} cy={30} r={7} className="stage-pad-ring" />
            <circle cx={s.x} cy={30} r={3} className="stage-pad-core" />
          </g>
        ))}
      </svg>
      <div className="stage-trace-labels" aria-hidden="true">
        {STATIONS.map((s, i) => (
          <span key={s.id} className={i <= index && phase !== "idle" ? "is-lit" : ""} style={{ left: `${s.x / 10}%` }}>
            {s.label}
          </span>
        ))}
      </div>
      <span className="sr-only" aria-live="polite">
        {phase === "idle" ? "Ready" : phase === "error" ? "Stopped" : STATIONS[index].label}
      </span>
    </div>
  );
}

function activeIndex(stage: JobStage | null, phase: StageRailProps["phase"]) {
  if (phase === "done") return 4;
  if (stage === "inference") return 1;
  if (stage === "drc") return 2;
  if (stage === "bom") return 3;
  return 0;
}
