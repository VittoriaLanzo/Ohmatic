import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExportError, downloadTextFile, exportCircuit } from "./exportClient";
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
    const file = { filename: "led_blinker.kicad_sch", content_type: "application/x-kicad-schematic", content: "(kicad_sch)" };
    const fetchImpl = vi.fn(async () => jsonResponse(200, file));

    const result = await exportCircuit(circuit, "kicad_sch", fetchImpl as unknown as typeof fetch);

    expect(result).toEqual(file);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/v1/export");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ circuit, format: "kicad_sch" });
  });

  it("surfaces the server error message as an ExportError", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(422, { error: "unsupported_schema_version" }));
    await expect(exportCircuit(circuit, "netlist", fetchImpl as unknown as typeof fetch))
      .rejects.toThrowError(/unsupported_schema_version/);
    await expect(exportCircuit(circuit, "netlist", fetchImpl as unknown as typeof fetch))
      .rejects.toBeInstanceOf(ExportError);
  });
});

describe("downloadTextFile", () => {
  beforeEach(() => {
    (globalThis.URL as unknown as { createObjectURL: () => string }).createObjectURL = vi.fn(() => "blob:mock");
    (globalThis.URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = vi.fn();
  });

  it("creates an anchor named after the file and clicks it", () => {
    const anchor = document.createElement("a");
    const createSpy = vi.spyOn(document, "createElement").mockReturnValue(anchor);
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);

    downloadTextFile({ filename: "led_blinker.net", content_type: "application/x-kicad-netlist", content: "(export)" });

    expect(createSpy).toHaveBeenCalledWith("a");
    expect(anchor.download).toBe("led_blinker.net");
    expect(click).toHaveBeenCalledOnce();
    vi.restoreAllMocks();
  });
});
