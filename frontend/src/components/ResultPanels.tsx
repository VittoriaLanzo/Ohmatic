import { AlertTriangle, Copy, FileJson, PackageSearch } from "lucide-react";
import { useMemo, useState } from "react";
import { formatCurrency, formatMs } from "../lib/format";
import type { GenerateResult } from "../types/api";

type ResultPanelsProps = {
  result: GenerateResult | null;
};

type TabId = "warnings" | "bom" | "json";

export function ResultPanels({ result }: ResultPanelsProps) {
  const [activeTab, setActiveTab] = useState<TabId>("warnings");
  // JSON VISUALIZATION TODO:
  // The Contract tab currently pretty-prints result.circuit as read-only JSON.
  // Replace this with a schema-aware JSON tree/editor before production workflows depend on it:
  // collapsible nodes, schema highlighting, validation state, copy/download, and large-payload safeguards.
  const json = useMemo(() => (result ? JSON.stringify(result.circuit, null, 2) : ""), [result]);
  const displayedParts = useMemo(() => {
    // BOM ENTRY: prefer backend result.bom from the gateway job result.
    // If BOM is empty, derive temporary rows from result.circuit.components so the Parts tab
    // remains data-driven while the backend enricher is still catching up.
    if (!result) {
      return [];
    }
    if (result.bom.length > 0) {
      return result.bom.map((entry) => ({
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
    <section className="inspector-panel" aria-labelledby="inspector-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Artifact package</p>
          <h2 id="inspector-heading">Review bundle</h2>
        </div>
        <div className="latency-strip" aria-label="Artifact timing">
          <span>Inference {formatMs(result?.latency_ms.inference)}</span>
          <span>DRC {formatMs(result?.latency_ms.drc)}</span>
          <span>BOM {formatMs(result?.latency_ms.bom)}</span>
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
          {!result ? (
            <p className="muted">Parts appear here when the circuit artifact is ready.</p>
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
                {displayedParts.map((entry) => (
                  <tr key={entry.id}>
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
        </div>
      )}

      {activeTab === "json" && (
        <div className="tab-panel json-panel" role="tabpanel">
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
