import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useProcurement } from "./useProcurement";
import type { GatewayApi } from "../../api/gateway";
import type { PartsListRow, ProcurementResponse } from "../../types/api";

const PARTS: PartsListRow[] = [
  {
    id: "C1",
    type: "capacitor",
    parts_list_part: "capacitor",
    value: "100nF",
    package: "0603",
    description: "capacitor 100nF 0603",
    is_part: true,
    match_status: "local_only"
  }
];

const SAMPLE: ProcurementResponse = {
  procurement_status: "links_ready",
  link_actions: [
    {
      type: "open_search_link",
      part_id: "C1",
      supplier: "digikey",
      quantity: 1,
      url: "https://www.digikey.com/en/products?keywords=capacitor+100nF+0603",
      label: "Search DigiKey for C1"
    }
  ],
  eligibility_disclosures: []
};

function fakeApi(data: ProcurementResponse): GatewayApi {
  return {
    createGeneration: vi.fn(),
    getJobStatus: vi.fn(),
    checkHealth: vi.fn(),
    getProcurementMatches: vi.fn().mockResolvedValue(data)
  } as unknown as GatewayApi;
}

describe("useProcurement", () => {
  it("does not hit the backend while the lever is off", () => {
    const api = fakeApi(SAMPLE);
    renderHook(() => useProcurement(PARTS, false, api));
    expect(api.getProcurementMatches).not.toHaveBeenCalled();
  });

  it("fetches disclosed supplier link-outs when the lever is on", async () => {
    const api = fakeApi(SAMPLE);
    const { result } = renderHook(() => useProcurement(PARTS, true, api));

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(api.getProcurementMatches).toHaveBeenCalledTimes(1);
    if (result.current.status === "ready") {
      expect(result.current.data.link_actions[0].label).toBe("Search DigiKey for C1");
    }
  });
});
