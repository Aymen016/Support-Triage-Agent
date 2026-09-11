export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.max(0, Math.round((now - then) / 1000));

  if (diffSec < 60) return "just now";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

export function RelativeTime({ iso, className = "" }: { iso: string; className?: string }) {
  return (
    <span className={`tabular text-xs text-[var(--color-ink-faint)] ${className}`} title={new Date(iso).toLocaleString()}>
      {relativeTime(iso)}
    </span>
  );
}
