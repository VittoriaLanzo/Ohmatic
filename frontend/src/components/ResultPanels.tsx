import { AlertTriangle, Copy, FileJson, Info, PackageSearch } from "lucide-react";
import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { formatCurrency, formatMs } from "../lib/format";
import type { GenerateResult } from "../types/api";
import { ProcurementLever } from "./ProcurementLever";
import { useProcurement } from "../features/procurement/useProcurement";

type ResultPanelsProps = {
  result: GenerateResult | null;
  phase: "idle" | "submitting" | "polling" | "done" | "error";
};

type TabId = "warnings" | "bom" | "json";

const PROC_KEY = "ohmatic.procurement-online";

export function ResultPanels({ result, phase }: ResultPanelsProps) {
  const [activeTab, setActiveTab] = useState<TabId>("warnings");
  const [online, setOnline] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(PROC_KEY) === "1";
    } catch {
      return false;
    }
  });
  const handleOnline = (next: boolean) => {
    setOnline(next);
    try {
      window.localStorage.setItem(PROC_KEY, next ? "1" : "0");
    } catch {
      // storage unavailable: the opt-in resets to off on next load, which is the safe default
    }
  };
  const procurement = useProcurement(result?.parts_list, online);
  // JSON VISUALIZATION TODO: Contract tab pretty-prints result.circuit as read-only
  // JSON. Replace with a schema-aware tree/editor (collapsible nodes, validation,
  // copy/download, large-payload safeguards) before production depends on it.
  const json = useMemo(() => (result ? JSON.stringify(result.circuit, null, 2) : ""), [result]);
  const displayedParts = useMemo(() => {
    // BOM ENTRY: prefer backend result.bom; if empty, derive temporary rows from
    // result.circuit.components so the Parts tab stays data-driven meanwhile.
    if (!result) {
      return [];
    }
    if ((result.bom?.length ?? 0) > 0) {
      return result.bom!.map((entry) => ({
        id: entry.id,
        mpn: entry.mpn ?? "unresolved",
        description: entry.description,
        price: formatCurrency(entry.price_usd),
        source: entry.mpn_found ? "matched" : "symbol"
      }));
    }
    return result.circuit.components.map((component) => ({
      id: component.id,
      mpn: component.part || "symbol",
      description: `${component.type}${component.value ? ` - ${component.value}` : ""}`,
      price: "pending",
      source: "derived"
    }));
  }, [result]);

  return (
    <section className={`inspector-panel is-${phase}`} aria-labelledby="inspector-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Checked, listed, signed</p>
          <h2 id="inspector-heading">Verification report</h2>
        </div>
        <div className="latency-strip" aria-label="Artifact timing">
          <span>Inference {formatMs(result?.latency_ms.inference)}</span>
          <span>DRC {formatMs(result?.latency_ms.drc)}</span>
          {result?.latency_ms.parts_list != null ? (
            <span>Parts {formatMs(result.latency_ms.parts_list)}</span>
          ) : (
            <span>BOM {formatMs(result?.latency_ms.bom)}</span>
          )}
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Result panels">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "warnings"}
          className={activeTab === "warnings" ? "is-selected" : ""}
          onClick={() => setActiveTab("warnings")}
        >
          <AlertTriangle size={16} aria-hidden="true" />
          Checks
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "bom"}
          className={activeTab === "bom" ? "is-selected" : ""}
          onClick={() => setActiveTab("bom")}
        >
          <PackageSearch size={16} aria-hidden="true" />
          Parts
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "json"}
          className={activeTab === "json" ? "is-selected" : ""}
          onClick={() => setActiveTab("json")}
        >
          <FileJson size={16} aria-hidden="true" />
          Contract
        </button>
      </div>

      {activeTab === "warnings" && (
        <output className="tab-panel" role="tabpanel">
          {!result ? (
            <p className="muted">Verification checks appear here after the circuit is accepted.</p>
          ) : result.drc_warnings.length === 0 ? (
            <p className="success-note">No DRC warnings. The circuit passed the visible checks.</p>
          ) : (
            <ul className="warning-list">
              {result.drc_warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
        </output>
      )}

      {activeTab === "bom" && (
        <div className="tab-panel" role="tabpanel">
          <ProcurementLever online={online} onChange={handleOnline} />
          {!result ? (
            <p className="muted">Parts appear here when the circuit artifact is ready.</p>
          ) : (result.parts_list?.length ?? 0) > 0 ? (
            // Deterministic local parts_list: supplier-free by design (no MPN/price -
            // procurement is a separate, disclosed link-out layer).
            <table>
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Description</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {result.parts_list!.map((row, index) => (
                  <tr key={row.id} style={{ "--row-order": index } as CSSProperties}>
                    <th scope="row">{row.id}</th>
                    <td>{row.description}</td>
                    <td>
                      {row.is_part ? (
                        <span className="source-chip is-part">part</span>
                      ) : (
                        <span className="rail-status">
                          <span className="source-chip is-rail">power rail</span>
                          <button
                            type="button"
                            className="info-dot"
                            aria-label="Schematic rail label, not a purchasable part"
                            title="Schematic rail label, not a purchasable part"
                          >
                            <Info size={13} aria-hidden="true" />
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table>
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">MPN</th>
                  <th scope="col">Description</th>
                  <th scope="col">Price</th>
                  <th scope="col">Source</th>
                </tr>
              </thead>
              <tbody>
                {displayedParts.map((entry, index) => (
                  <tr key={entry.id} style={{ "--row-order": index } as CSSProperties}>
                    <th scope="row">{entry.id}</th>
                    <td>{entry.mpn}</td>
                    <td>{entry.description}</td>
                    <td>{entry.price}</td>
                    <td>
                      <span className={`source-chip is-${entry.source}`}>{entry.source}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {online && procurement.status !== "idle" && (
            <div className="proc-links">
              {procurement.status === "loading" && <p className="muted">Looking up suppliers.</p>}
              {procurement.status === "error" && <p className="muted">{procurement.message}</p>}
              {procurement.status === "ready" &&
                (procurement.data.link_actions.length > 0 ? (
                  <>
                    <p className="eyebrow">Buy links</p>
                    <ul className="proc-link-list">
                      {procurement.data.link_actions.map((action) => (
                        <li key={`${action.part_id}-${action.url}`}>
                          <a href={action.url} target="_blank" rel="noopener noreferrer">
                            {action.label}
                          </a>
                          {action.disclosure && (
                            <span className="proc-disclosure">{action.disclosure}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                    {procurement.data.eligibility_disclosures.map((disclosure) => (
                      <p key={disclosure} className="proc-disclosure">
                        {disclosure}
                      </p>
                    ))}
                  </>
                ) : (
                  <p className="muted">No parts to look up.</p>
                ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "json" && (
        <div className="tab-panel json-panel" role="tabpanel">
          <span className="json-scanline" aria-hidden="true" />
          <button
            className="icon-button"
            type="button"
            disabled={!json}
            aria-label="Copy contract JSON"
            title="Copy contract JSON"
            onClick={() => void navigator.clipboard?.writeText(json)}
          >
            <Copy size={16} aria-hidden="true" />
          </button>
          <pre tabIndex={0}>{json || "{\n  \"contract\": \"waiting for verified circuit\"\n}"}</pre>
        </div>
      )}
    </section>
  );
}
