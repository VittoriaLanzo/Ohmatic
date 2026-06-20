import type { OhmaticCircuitV01 } from "../../types/circuit";

// KiCad export surface for the browser. The circuit already lives client-side after
// a finished job, so export is a single same-origin POST: Vite proxies /v1/export to
// the loopback exporter service (:8004), keeping the browser on one base URL exactly
// like the gateway calls. Contract: shared/docs/contracts.md sections 10-11.

export type ExportFormatId = "kicad_sch" | "netlist";

export type ExportFormat = {
  id: ExportFormatId;
  label: string;
  ext: string;
  description: string;
};

// Mirrors GET /v1/export/capabilities (exporter/emit/export.py). Inlined for an
// instant menu; the server stays the source of truth for what actually renders.
export const EXPORT_FORMATS: ExportFormat[] = [
  {
    id: "kicad_sch",
    label: "KiCad schematic",
    ext: ".kicad_sch",
    description: "Editable schematic. Opens in KiCad."
  },
  {
    id: "netlist",
    label: "Netlist",
    ext: ".net",
    description: "Components and nets. Import into Pcbnew."
  }
];

export type ExportFile = {
  filename: string;
  content_type: string;
  content: string;
};

export class ExportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExportError";
  }
}

export async function exportCircuit(
  circuit: OhmaticCircuitV01,
  format: ExportFormatId,
  fetchImpl: typeof fetch = fetch.bind(globalThis)
): Promise<ExportFile> {
  const response = await fetchImpl("/v1/export", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ circuit, format })
  });

  const text = await response.text();
  const payload = text ? safeJson(text) : {};
  if (!response.ok) {
    const message =
      isObject(payload) && typeof payload.error === "string"
        ? payload.error
        : `Export failed (HTTP ${response.status})`;
    throw new ExportError(message);
  }
  return payload as ExportFile;
}

// Stream the returned text straight to a browser download. Kept separate from the
// fetch so the network path stays unit-testable without a DOM.
export function downloadTextFile(file: ExportFile): void {
  const blob = new Blob([file.content], {
    type: file.content_type || "application/octet-stream"
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoke after the click resolves so the download is not cancelled mid-flight.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
