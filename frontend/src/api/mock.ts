import type { GatewayApi } from "./gateway";
import type { GenerateRequest, JobStatusResponse } from "../types/api";
import type { OhmaticCircuitV01 } from "../types/circuit";

const mockCircuit: OhmaticCircuitV01 = {
  metadata: {
    title: "LED Current Limiter",
    description: "A 5V rail driving an LED through a current-limiting resistor.",
    version: "0.1",
    tags: ["led", "resistor", "demo"]
  },
  components: [
    {
      id: "VCC1",
      type: "power_vcc",
      value: "5V",
      part: "VCC",
      x: 24,
      y: 42,
      pins: { "1": "VCC" }
    },
    {
      id: "R1",
      type: "resistor",
      value: "330 ohm",
      part: "0603",
      x: 118,
      y: 42,
      pins: { "1": "VCC", "2": "LED_A" }
    },
    {
      id: "D1",
      type: "led",
      value: "green",
      part: "0603",
      x: 212,
      y: 42,
      pins: { A: "LED_A", K: "GND" }
    },
    {
      id: "GND1",
      type: "power_gnd",
      value: "",
      part: "GND",
      x: 300,
      y: 42,
      pins: { "1": "GND" }
    }
  ],
  nets: [
    { name: "VCC", pins: ["VCC1.1", "R1.1"] },
    { name: "LED_A", pins: ["R1.2", "D1.A"] },
    { name: "GND", pins: ["D1.K", "GND1.1"] }
  ]
};

export function createMockGatewayApi(): GatewayApi {
  let prompt = "LED with 330 ohm resistor";
  let pollCount = 0;

  return {
    async createGeneration(request: GenerateRequest) {
      prompt = request.prompt;
      pollCount = 0;
      return {
        job_id: "mock-job-01",
        poll_url: "/v1/jobs/mock-job-01/status"
      };
    },

    async getJobStatus(): Promise<JobStatusResponse> {
      pollCount += 1;
      if (pollCount === 1) {
        return { status: "pending", stage: null, result: null, error: null };
      }
      if (pollCount === 2) {
        return { status: "running", stage: "inference", result: null, error: null };
      }
      if (pollCount === 3) {
        return { status: "running", stage: "drc", result: null, error: null };
      }
      return {
        status: "done",
        stage: null,
        error: null,
        result: {
          circuit: {
            ...mockCircuit,
            metadata: {
              ...mockCircuit.metadata,
              description: `Mock result for: ${prompt}`
            }
          },
          drc_warnings: [],
          bom: [
            {
              id: "R1",
              mpn: "RC0603FR-07330RL",
              description: "330 ohm resistor, 1%, 0603",
              price_usd: 0.01,
              url: null,
              mpn_found: true
            },
            {
              id: "D1",
              mpn: "LTST-C190KGKT",
              description: "Green LED, 0603",
              price_usd: 0.03,
              url: null,
              mpn_found: true
            }
          ],
          latency_ms: { inference: 1280, drc: 18, bom: 42 }
        }
      };
    },

    async checkHealth() {
      return { status: "ok" };
    }
  };
}
