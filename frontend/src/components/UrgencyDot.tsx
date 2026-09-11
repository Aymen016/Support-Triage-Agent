import type { Urgency } from "../lib/api";

const COLOR: Record<Urgency, string> = {
  high: "var(--color-urgent-high)",
  medium: "var(--color-urgent-medium)",
  low: "var(--color-urgent-low)",
};

const LABEL: Record<Urgency, string> = { high: "High urgency", medium: "Medium urgency", low: "Low urgency" };

export function UrgencyDot({ urgency, className = "" }: { urgency: Urgency | null; className?: string }) {
  if (!urgency) {
    return <span className={`inline-block w-2 h-2 rounded-full bg-[var(--color-border-strong)] ${className}`} aria-label="Urgency unknown" />;
  }
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full shrink-0 ${className}`}
      style={{ backgroundColor: COLOR[urgency] }}
      aria-label={LABEL[urgency]}
      title={LABEL[urgency]}
    />
  );
}
