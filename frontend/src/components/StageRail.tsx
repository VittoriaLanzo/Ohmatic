import type { CSSProperties } from "react";
import type { JobStage } from "../types/api";

type StageRailProps = {
  stage: JobStage | null;
  phase: "idle" | "submitting" | "polling" | "done" | "error";
};

// PIPELINE UI ENTRY: maps backend job `stage` values from GET /v1/jobs/{id}/status
// to the progress bar. Add new backend stages here if the gateway contract grows.
const STAGES: { id: string; label: string; progress: number }[] = [
  { id: "queued", label: "Queued", progress: 0.08 },
  { id: "inference", label: "Generating circuit", progress: 0.38 },
  { id: "drc", label: "Running rule checks", progress: 0.66 },
  { id: "bom", label: "Building parts list", progress: 0.88 },
  { id: "done", label: "Done", progress: 1 }
];

export function StageRail({ stage, phase }: StageRailProps) {
  const index = activeIndex(stage, phase);
  const current = STAGES[index];
  const busy = phase === "submitting" || phase === "polling";
  const progress = phase === "done" ? 1 : phase === "idle" ? 0 : current.progress;

  return (
    <div
      className={`stage-progress is-${phase}`}
      style={{ "--progress": progress } as CSSProperties}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(progress * 100)}
      aria-label="Generation pipeline"
    >
      <div className="stage-progress-track">
        <span className="stage-progress-fill" />
        <span className="stage-progress-flow" aria-hidden="true" />
        {STAGES.slice(1, 4).map((s) => (
          <span
            key={s.id}
            className={`stage-progress-tick ${progress >= s.progress ? "is-passed" : ""}`}
            style={{ left: `${s.progress * 100}%` }}
            aria-hidden="true"
          />
        ))}
        <span className="stage-progress-head" aria-hidden="true" />
      </div>
      <div className="stage-progress-meta" aria-live="polite">
        <span className="stage-progress-label" key={busy || phase === "done" ? current.label : "idle"}>
          {phase === "idle" ? "Ready" : phase === "error" ? "Stopped — see message above" : current.label}
        </span>
        {busy && <span className="stage-progress-pct">{Math.round(progress * 100)}%</span>}
      </div>
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
