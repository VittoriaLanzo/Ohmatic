export function formatMs(value?: number): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)}s`;
  }
  return `${Math.round(value)}ms`;
}

export function formatCurrency(value: number | null): string {
  if (value === null) {
    return "n/a";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4
  }).format(value);
}

export function humanizeStage(stage: string | null): string {
  if (!stage) {
    return "Ready";
  }
  return stage.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
