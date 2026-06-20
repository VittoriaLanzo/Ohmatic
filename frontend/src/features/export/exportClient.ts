import type { OhmaticCircuitV01 } from "../../types/circuit";

// KiCad export surface for the browser. The circuit already lives client-side after
// a finished job, so export is a single same-origin POST: Vite proxies /v1/export to
// the loopback exporter service (:8004), keeping the browser on one base URL exactly
// like the gateway calls. Contract: shared/docs/contracts.md sections 10-11.

export type ExportFormatId = "kicad_project" | "netlist";

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
    id: "kicad_project",
    label: "KiCad project",
    ext: ".zip",
    description: "Schematic + library. Opens clean in KiCad."
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
  // "utf-8" for text formats (netlist); "base64" for binary ones (the project zip).
  encoding?: "utf-8" | "base64";
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

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(b64);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

// Stream the returned file straight to a browser download. Handles both text
// formats and base64-encoded binary (the project zip). Kept separate from the fetch
// so the network path stays unit-testable without a DOM.
export function downloadExport(file: ExportFile): void {
  const body: BlobPart = file.encoding === "base64" ? base64ToBytes(file.content) : file.content;
  const blob = new Blob([body], {
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
