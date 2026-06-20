import { ChevronDown, CircuitBoard, Download, FileCode2, Loader2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import {
  EXPORT_FORMATS,
  ExportError,
  downloadTextFile,
  exportCircuit,
  type ExportFormatId
} from "../features/export/exportClient";
import type { OhmaticCircuitV01 } from "../types/circuit";

const FORMAT_ICON: Record<ExportFormatId, typeof CircuitBoard> = {
  kicad_sch: CircuitBoard,
  netlist: FileCode2
};

type ExportButtonProps = {
  circuit: OhmaticCircuitV01 | null;
};

// Toolbar sibling to the ANSI/IEC toggle: a compiler emits an artifact. One click
// per format streams the file straight to the browser's downloads, no detour.
export function ExportButton({ circuit }: ExportButtonProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ExportFormatId | null>(null);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const disabled = circuit === null;

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent) {
      if (root.current && !root.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function runExport(format: ExportFormatId) {
    if (!circuit) {
      return;
    }
    setBusy(format);
    setError(null);
    try {
      const file = await exportCircuit(circuit, format);
      downloadTextFile(file);
      setOpen(false);
    } catch (cause) {
      setError(cause instanceof ExportError ? cause.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="export-control" ref={root}>
      <button
        type="button"
        className="export-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        disabled={disabled}
        title={disabled ? "Compile a circuit first" : "Export to KiCad"}
        onClick={() => setOpen((value) => !value)}
      >
        {busy ? (
          <Loader2 size={16} className="export-spin" aria-hidden="true" />
        ) : (
          <Download size={16} aria-hidden="true" />
        )}
        <span>Export</span>
        <ChevronDown size={14} className="export-caret" aria-hidden="true" />
      </button>

      {open && (
        <div className="export-menu" id={menuId} role="menu" aria-label="KiCad export formats">
          <p className="export-menu__title">Emit artifact</p>
          {EXPORT_FORMATS.map((format) => {
            const Icon = FORMAT_ICON[format.id];
            return (
              <button
                key={format.id}
                type="button"
                role="menuitem"
                className="export-menu__item"
                disabled={busy !== null}
                onClick={() => void runExport(format.id)}
              >
                <Icon size={18} aria-hidden="true" />
                <span className="export-menu__text">
                  <span className="export-menu__label">
                    {format.label}
                    <code className="export-menu__ext">{format.ext}</code>
                  </span>
                  <span className="export-menu__desc">{format.description}</span>
                </span>
                {busy === format.id && <Loader2 size={14} className="export-spin" aria-hidden="true" />}
              </button>
            );
          })}
          {error && (
            <p className="export-menu__error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
