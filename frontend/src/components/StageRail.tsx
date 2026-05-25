import { CheckCircle2, CircleDashed, Cpu, PackageCheck, ShieldCheck, Zap } from "lucide-react";
import type { CSSProperties } from "react";
import type { JobStage } from "../types/api";

type StageRailProps = {
  stage: JobStage | null;
  phase: "idle" | "submitting" | "polling" | "done" | "error";
};

const stages = [
  { id: "queued", label: "Queued", icon: CircleDashed },
  { id: "inference", label: "Inference", icon: Cpu },
  { id: "drc", label: "DRC", icon: ShieldCheck },
  { id: "bom", label: "BOM", icon: PackageCheck },
  { id: "done", label: "Done", icon: CheckCircle2 }
] as const;

export function StageRail({ stage, phase }: StageRailProps) {
  // PIPELINE UI ENTRY: maps backend job `stage` values from GET /v1/jobs/{id}/status
  // to the visible progress rail. Add new backend stages here if the gateway contract grows.
  const activeIndex = getActiveIndex(stage, phase);
  const railStyle = { "--active-index": activeIndex } as CSSProperties;

  return (
    <ol className={`stage-rail is-${phase}`} style={railStyle} aria-label="Generation pipeline">
      <span className="stage-bus" aria-hidden="true" />
      <span className="stage-bus-charge" aria-hidden="true" />
      <span className="stage-bus-packet" aria-hidden="true" />
      {stages.map((item, index) => {
        const Icon = item.icon;
        const state = index < activeIndex ? "complete" : index === activeIndex ? "active" : "waiting";
        return (
          <li
            className={`stage-step is-${state} stage-${item.id}`}
            key={item.id}
            style={{ "--stage-order": index } as CSSProperties}
          >
            <span className="stage-icon" aria-hidden="true">
              {state === "active" && phase !== "done" && phase !== "idle" ? <Zap size={15} /> : <Icon size={15} />}
            </span>
            <span>{item.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function getActiveIndex(stage: JobStage | null, phase: StageRailProps["phase"]) {
  if (phase === "done") {
    return stages.length - 1;
  }
  if (phase === "submitting") {
    return 0;
  }
  if (phase === "error") {
    return 0;
  }
  if (stage === "inference") {
    return 1;
  }
  if (stage === "drc") {
    return 2;
  }
  if (stage === "bom") {
    return 3;
  }
  return 0;
}
