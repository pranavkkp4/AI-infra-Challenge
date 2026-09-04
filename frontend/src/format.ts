export function label(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function shortDate(value: string | null): string {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function compactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: "compact" }).format(value);
}

export function riskBand(score: number): "critical" | "watch" | "stable" {
  if (score >= 65) return "critical";
  if (score >= 40) return "watch";
  return "stable";
}
