import type { JobStage } from "../types/api";

type OhmaticLogoProps = {
  stage: JobStage | null;
  phase: "idle" | "submitting" | "polling" | "done" | "error";
  active: boolean;
  returning: boolean;
};

export function OhmaticLogo({ stage, phase, active, returning }: OhmaticLogoProps) {
  const signal = phase === "polling" && stage ? stage : phase;

  return (
    <svg
      className={`ohmatic-logo ${active ? "is-active" : ""} ${returning ? "is-returning" : ""} is-${signal} ${stage ? `is-${stage}` : ""}`}
      viewBox="0 0 380 100"
      role="img"
      aria-labelledby="ohmatic-logo-title ohmatic-logo-desc"
    >
      <title id="ohmatic-logo-title">Ohmatic</title>
      <desc id="ohmatic-logo-desc">Ohmatic wordmark drawn as circuit traces.</desc>
      <defs>
        <filter id="logo-glow" x="-20%" y="-80%" width="140%" height="260%">
          <feGaussianBlur stdDeviation="2.2" result="blur" />
          <feColorMatrix
            in="blur"
            type="matrix"
            values="0 0 0 0 0.290 0 0 0 0 0.870 0 0 0 0 0.500 0 0 0 0.86 0"
          />
          <feMerge>
            <feMergeNode />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <linearGradient id="logo-surge-gradient" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#4ade80" stopOpacity="0" />
          <stop offset="42%" stopColor="#4ade80" stopOpacity="0.92" />
          <stop offset="56%" stopColor="#e8ede0" stopOpacity="1" />
          <stop offset="100%" stopColor="#4ade80" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" rx="8" fill="#0d1117" />
      <rect className="logo-board-glow" x="1" y="1" width="378" height="98" rx="8" fill="none" />

      <g className="logo-base">
        <line x1="14" y1="80" x2="366" y2="80" stroke="#4ade80" strokeWidth="0.5" opacity="0.3" />
        <path
          d="M14 80 L22 80 L22 74 A32 32 0 1 1 62 74 L62 80 L70 80"
          stroke="#e8ede0"
          strokeWidth="3"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <line x1="80" y1="16" x2="80" y2="80" stroke="#e8ede0" strokeWidth="3" strokeLinecap="round" />
        <path d="M80 44 C80 28,118 28,118 80" stroke="#e8ede0" strokeWidth="3" fill="none" strokeLinecap="round" />
        <path
          d="M128 80 L146 20 L164 80 L182 20 L200 80"
          stroke="#e8ede0"
          strokeWidth="3"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <line x1="210" y1="80" x2="231" y2="16" stroke="#e8ede0" strokeWidth="3" strokeLinecap="round" />
        <line x1="252" y1="80" x2="231" y2="16" stroke="#e8ede0" strokeWidth="3" strokeLinecap="round" />
        <line x1="218" y1="56" x2="244" y2="56" stroke="#e8ede0" strokeWidth="3" strokeLinecap="round" />
        <line x1="277" y1="28" x2="277" y2="80" stroke="#e8ede0" strokeWidth="3" strokeLinecap="round" />
        <line x1="263" y1="44" x2="291" y2="44" stroke="#e8ede0" strokeWidth="3" strokeLinecap="round" />
        <circle cx="309" cy="14" r="3.5" fill="#e8ede0" className="logo-node" />
        <line x1="309" y1="20" x2="309" y2="80" stroke="#e8ede0" strokeWidth="3" strokeLinecap="round" />
        <line x1="303" y1="80" x2="315" y2="80" stroke="#e8ede0" strokeWidth="3" strokeLinecap="round" />
        <path d="M325 40 L337 40 A30 30 0 0 1 337 76 L325 76" stroke="#e8ede0" strokeWidth="3" fill="none" strokeLinecap="round" />
        <circle cx="99" cy="34" r="4.5" fill="#4ade80" className="logo-node" />
        <circle cx="146" cy="20" r="4" fill="#4ade80" className="logo-node" />
        <circle cx="182" cy="20" r="4" fill="#4ade80" className="logo-node" />
        <circle cx="231" cy="16" r="4.5" fill="#4ade80" className="logo-node" />
        <circle cx="277" cy="44" r="4" fill="#4ade80" className="logo-node" />
      </g>

      <g className="logo-current" aria-hidden="true">
        <path className="spark spark-baseline" pathLength="1" d="M14 80 L366 80" />
        <path className="spark spark-omega" pathLength="1" d="M14 80 L22 80 L22 74 A32 32 0 1 1 62 74 L62 80 L70 80" />
        <path className="spark spark-h" pathLength="1" d="M80 16 L80 80 M80 44 C80 28,118 28,118 80" />
        <path className="spark spark-m" pathLength="1" d="M128 80 L146 20 L164 80 L182 20 L200 80" />
        <path className="spark spark-a" pathLength="1" d="M210 80 L231 16 L252 80 M218 56 L244 56" />
        <path className="spark spark-t" pathLength="1" d="M277 28 L277 80 M263 44 L291 44" />
        <path className="spark spark-i" pathLength="1" d="M309 20 L309 80 M303 80 L315 80" />
        <path className="spark spark-c" pathLength="1" d="M325 40 L337 40 A30 30 0 0 1 337 76 L325 76" />
      </g>
      <g className="logo-surge" aria-hidden="true" filter="url(#logo-glow)">
        <path pathLength="1" d="M14 80 L70 80 L80 44 C80 28,118 28,118 80 L128 80 L146 20 L164 80 L182 20 L200 80 L218 56 L244 56 L277 44 L309 20 L325 40 L337 40 A30 30 0 0 1 337 76 L366 80" />
      </g>
      <g className="logo-diagnostic" aria-hidden="true">
        <circle cx="99" cy="34" r="7" />
        <circle cx="146" cy="20" r="6.5" />
        <circle cx="182" cy="20" r="6.5" />
        <circle cx="231" cy="16" r="7" />
        <circle cx="277" cy="44" r="6.5" />
        <circle cx="309" cy="14" r="6.5" />
      </g>
    </svg>
  );
}
