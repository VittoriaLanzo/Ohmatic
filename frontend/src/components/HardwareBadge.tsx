import { useEffect, useState } from "react";

type Doctor = {
  ram_gb?: number;
  vram_mb?: number;
  gpu?: string;
  recommended_model: string;
  reason: string;
};

type WebGpuState = "checking" | "active" | "unavailable";

const TIER_LABEL: Record<string, string> = {
  bf16: "bf16 (full, GPU)",
  q8_0: "Q8_0 GGUF (GPU)",
  q4_k_m: "Q4_K_M GGUF (GPU)",
  q4_k_m_cpu: "Q4_K_M GGUF (CPU)",
  stub: "stub / cloud"
};

/** Auto-runs on load: verifies WebGPU is actually activatable (adapter request,
 *  not just `navigator.gpu` presence) and fetches the `ohmatic doctor` hardware
 *  verdict so the user sees which model this machine will load. */
export function HardwareBadge() {
  const [webgpu, setWebgpu] = useState<WebGpuState>("checking");
  const [doctor, setDoctor] = useState<Doctor | null>(null);

  useEffect(() => {
    const nav = navigator as Navigator & {
      gpu?: { requestAdapter(): Promise<unknown | null> };
    };
    if (!nav.gpu) {
      setWebgpu("unavailable");
      return;
    }
    nav.gpu
      .requestAdapter()
      .then((adapter) => setWebgpu(adapter ? "active" : "unavailable"))
      .catch(() => setWebgpu("unavailable"));
  }, []);

  useEffect(() => {
    fetch("/v1/doctor")
      .then((r) => (r.ok ? r.json() : null))
      .then((d: Doctor | null) => setDoctor(d))
      .catch(() => setDoctor(null));
  }, []);

  const gpuPart =
    doctor?.vram_mb && doctor.vram_mb > 0
      ? ` · ${doctor.gpu || "GPU"} ${(doctor.vram_mb / 1024).toFixed(0)} GB`
      : "";

  return (
    <div className="hw-badge" title={doctor?.reason ?? "hardware check"}>
      <span className={`hw-webgpu hw-webgpu-${webgpu}`}>
        WebGPU {webgpu === "active" ? "✓" : webgpu === "checking" ? "…" : "✗"}
      </span>
      {doctor && (
        <span>
          {doctor.ram_gb ? ` · ${doctor.ram_gb} GB RAM` : ""}
          {gpuPart} · model: {TIER_LABEL[doctor.recommended_model] ?? doctor.recommended_model}
        </span>
      )}
    </div>
  );
}
