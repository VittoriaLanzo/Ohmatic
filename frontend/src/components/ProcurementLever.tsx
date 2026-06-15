import { Lock } from "lucide-react";

type ProcurementLeverProps = {
  online: boolean;
  onChange: (next: boolean) => void;
};

/** Opt-in lever for online procurement. OFF (default) keeps everything local; ON allows
 *  part searches to reach component suppliers. The schematic never leaves the machine either way. */
export function ProcurementLever({ online, onChange }: ProcurementLeverProps) {
  return (
    <div className={`proc-lever ${online ? "is-on" : ""}`}>
      <div className="proc-lever__row">
        <button
          type="button"
          className="proc-switch"
          role="switch"
          aria-checked={online}
          aria-label="Online procurement"
          onClick={() => onChange(!online)}
        >
          <span className="proc-knob" aria-hidden="true" />
        </button>
        <div className="proc-readout">
          <span className="proc-led" aria-hidden="true" />
          <span className="proc-state">{online ? "ONLINE" : "OFFLINE"}</span>
          <span className="proc-sub">{online ? "live lookups" : "totally offline"}</span>
        </div>
      </div>
      <p className="proc-note">
        <Lock size={14} aria-hidden="true" />
        Your schematic stays on this machine. Only part searches are ever sent.
      </p>
    </div>
  );
}
