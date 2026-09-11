import { TriangleAlert } from "lucide-react";

const LOW_CONFIDENCE_THRESHOLD = 0.6;

export function ConfidenceBar({ value, showLabel = true }: { value: number | null; showLabel?: boolean }) {
  if (value === null) return <span className="text-xs text-[var(--color-ink-faint)]">—</span>;

  const isLow = value < LOW_CONFIDENCE_THRESHOLD;
  const pct = Math.round(value * 100);

  return (
    <span className="inline-flex items-center gap-1.5">
      {isLow && <TriangleAlert size={12} className="text-[var(--color-urgent-medium)]" aria-hidden />}
      <span className="w-10 h-1.5 rounded-full bg-[var(--color-border)] overflow-hidden inline-block">
        <span
          className="block h-full rounded-full"
          style={{
            width: `${pct}%`,
            backgroundColor: isLow ? "var(--color-urgent-medium)" : "var(--color-accent)",
          }}
        />
      </span>
      {showLabel && (
        <span className={`tabular text-xs ${isLow ? "text-[var(--color-urgent-medium)]" : "text-[var(--color-ink-muted)]"}`}>
          {pct}%
        </span>
      )}
    </span>
  );
}
