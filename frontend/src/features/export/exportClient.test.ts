import { afterEach, describe, expect, it, vi } from "vitest";
import { ExportError, downloadExport, exportCircuit } from "./exportClient";
import type { OhmaticCircuitV01 } from "../../types/circuit";

const circuit: OhmaticCircuitV01 = {
  metadata: { title: "LED blinker", description: "", version: "0.1", tags: ["t"] },
  components: [{ id: "R1", type: "resistor", value: "10k", part: "0603", x: 0, y: 0, pins: { "1": "1", "2": "2" } }],
  nets: [{ name: "N1", pins: ["R1.1", "R1.2"] }]
};

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(body) } as Response;
}

describe("exportCircuit", () => {
  it("POSTs the circuit and format to the same-origin /v1/export and returns the file", async () => {
    const file = { filename: "led_blinker.zip", content_type: "application/zip", content: "UEsDBA==", encoding: "base64" };
    const fetchImpl = vi.fn(async () => jsonResponse(200, file));

    const result = await exportCircuit(circuit, "kicad_project", fetchImpl as unknown as typeof fetch);

    expect(result).toEqual(file);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/v1/export");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ circuit, format: "kicad_project" });
  });

  it("surfaces the server error message as an ExportError", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(422, { error: "unsupported_schema_version" }));
    await expect(exportCircuit(circuit, "netlist", fetchImpl as unknown as typeof fetch))
      .rejects.toThrowError(/unsupported_schema_version/);
    await expect(exportCircuit(circuit, "netlist", fetchImpl as unknown as typeof fetch))
      .rejects.toBeInstanceOf(ExportError);
  });
});

describe("downloadExport", () => {
  function captureBlob() {
    let blob: Blob | null = null;
    (globalThis.URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL = vi.fn(
      (b: Blob) => {
        blob = b;
        return "blob:mock";
      }
    );
    (globalThis.URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = vi.fn();
    const anchor = document.createElement("a");
    vi.spyOn(document, "createElement").mockReturnValue(anchor);
    vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    return { anchor, getBlob: () => blob };
  }

  afterEach(() => vi.restoreAllMocks());

  it("decodes a base64 (zip) payload to bytes before downloading", () => {
    const { anchor, getBlob } = captureBlob();

    // "UEsDBA==" decodes to the 4-byte ZIP magic number (PK\x03\x04).
    downloadExport({ filename: "led_blinker.zip", content_type: "application/zip", content: "UEsDBA==", encoding: "base64" });

    const blob = getBlob();
    expect(blob).not.toBeNull();
    expect(blob?.size).toBe(4); // decoded bytes, not the 8-char base64 string
    expect(blob?.type).toBe("application/zip");
    expect(anchor.download).toBe("led_blinker.zip");
  });

  it("passes text payloads through unchanged", () => {
    const { getBlob } = captureBlob();

    downloadExport({ filename: "x.net", content_type: "application/x-kicad-netlist", content: "(export)", encoding: "utf-8" });

    expect(getBlob()?.size).toBe("(export)".length); // 8 bytes, no base64 round-trip
  });
});
