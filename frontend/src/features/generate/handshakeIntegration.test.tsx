import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useGenerateJob } from "./useGenerateJob";
import { SchematicSvg } from "../../components/SchematicSvg";
import type { GatewayApi } from "../../api/gateway";
import type { JobStatusResponse } from "../../types/api";
import type { OhmaticCircuitV01 } from "../../types/circuit";

// End-to-end without a model or RAM: mirror App's exact composition
//   const job = useGenerateJob(); <SchematicSvg circuit={job.result?.circuit ...}/>
// and drive the real HTTP handshake (submit -> poll -> done) through a mock gateway
// that returns a gateway-shaped result.circuit instantly. Proves the schematic
// engine plugs into the live data flow, not just isolated fixtures.

const circuit: OhmaticCircuitV01 = {
  metadata: { title: "LED blinker", description: "555 astable", version: "0.1", tags: [] },
  components: [
    { id: "U1", type: "ic_timer", value: "NE555", part: "DIP-8", x: 60, y: 50, pins: { VCC: "8", GND: "1", IN: "2", OUT: "3" } },
    { id: "R1", type: "resistor", value: "10k", part: "0603", x: 20, y: 20, pins: { "1": "1", "2": "2" } },
    { id: "C1", type: "capacitor", value: "10nF", part: "0805", x: 20, y: 80, pins: { "1": "1", "2": "2" } },
    { id: "LED1", type: "led", value: "", part: "", x: 95, y: 50, pins: { A: "A", K: "K" } },
    { id: "VCC1", type: "power_vcc", value: "5V", part: "VCC", x: 95, y: 10, pins: { "1": "1" } },
    { id: "GND1", type: "power_gnd", value: "", part: "GND", x: 95, y: 95, pins: { "1": "1" } },
  ],
  nets: [
    { name: "VCC", pins: ["VCC1.1", "U1.VCC", "R1.1"] },
    { name: "GND", pins: ["GND1.1", "U1.GND", "C1.2", "LED1.K"] },
    { name: "OUT", pins: ["U1.OUT", "LED1.A"] },
    { name: "TRIG", pins: ["U1.IN", "R1.2", "C1.1"] },
  ],
};

const doneStatus = {
  status: "done",
  stage: null,
  progress: 1,
  loops: 0,
  eta_s: null,
  elapsed_s: 1,
  result: { circuit, drc_warnings: [], parts_list: [], latency_ms: { inference: 100, drc: 0, bom: 0, parts_list: 0 } },
  error: null,
} as unknown as JobStatusResponse;

const mockApi = {
  createGeneration: async () => ({ job_id: "j1", poll_url: "/v1/jobs/j1/status" }),
  getJobStatus: async () => doneStatus,
  checkHealth: async () => ({ status: "ok" }),
  getProcurementMatches: async () => ({ matches: [] }),
} as unknown as GatewayApi;

function AppLikeHarness({ api }: { api: GatewayApi }) {
  const job = useGenerateJob(api);
  return (
    <div>
      <button onClick={() => void job.submit("1 Hz LED blink, 5 V", { temperature: 0.2 })}>generate</button>
      <SchematicSvg circuit={job.result?.circuit ?? null} phase={job.phase} symbolStyle="ansi" />
    </div>
  );
}

describe("gateway handshake renders into the schematic engine", () => {
  it("submit -> poll -> done draws the returned circuit in the real renderer", async () => {
    const { container } = render(<AppLikeHarness api={mockApi} />);

    // Before generation: the empty-schematic placeholder, no real components.
    expect(container.querySelector(".empty-schematic")).not.toBeNull();
    expect(container.querySelectorAll("[data-component-type]").length).toBe(0);

    fireEvent.click(screen.getByText("generate"));

    // After the handshake completes, the returned circuit renders.
    await waitFor(() => {
      expect(container.querySelectorAll("[data-component-type]").length).toBe(circuit.components.length);
    });

    const svg = container.querySelector("svg.schematic-svg")!;
    expect(svg.getAttribute("viewBox")).not.toBe("0 0 360 210"); // dynamic canvas
    expect(svg.classList.contains("is-done")).toBe(true); // animation phase wired through
    expect(container.querySelector('[data-symbol-kind="unknown"]')).toBeNull(); // every type drew a real symbol
    expect(container.querySelectorAll(".net-line").length).toBeGreaterThan(0); // nets routed
    expect(screen.queryByText("Pin ref issue")).toBeNull(); // a valid circuit shows no diagnostics
  });
});
