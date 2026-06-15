import { useEffect, useState } from "react";
import { createGatewayApi, type GatewayApi } from "../../api/gateway";
import { GatewayClientError } from "../../api/client";
import type { PartsListRow, ProcurementResponse } from "../../types/api";

const defaultApi = createGatewayApi();

export type ProcurementState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: ProcurementResponse }
  | { status: "error"; message: string };

/** Drives the online procurement lever. While the lever is off (or there is nothing buyable)
 *  it stays idle and makes no network call; when on it fetches disclosed supplier link-outs. */
export function useProcurement(
  partsList: PartsListRow[] | undefined,
  online: boolean,
  api: GatewayApi = defaultApi
): ProcurementState {
  const [state, setState] = useState<ProcurementState>({ status: "idle" });

  useEffect(() => {
    const buyable = (partsList ?? []).filter((row) => row.buyable);
    if (!online || buyable.length === 0) {
      setState({ status: "idle" });
      return;
    }

    let cancelled = false;
    setState({ status: "loading" });
    api
      .getProcurementMatches({ parts_list: partsList ?? [], supplier: "digikey" })
      .then((data) => {
        if (!cancelled) {
          setState({ status: "ready", data });
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        const message =
          error instanceof GatewayClientError
            ? error.detail.message
            : "Could not reach suppliers. Try again.";
        setState({ status: "error", message });
      });

    return () => {
      cancelled = true;
    };
  }, [online, partsList, api]);

  return state;
}
