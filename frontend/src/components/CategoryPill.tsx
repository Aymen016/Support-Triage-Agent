import type { Category } from "../lib/api";

const LABEL: Record<Category, string> = {
  bug_report: "Bug report",
  billing: "Billing",
  how_to: "How-to",
  sales: "Sales",
  spam: "Spam",
  other: "Other",
};

export function CategoryPill({ category }: { category: Category | null }) {
  if (!category) {
    return <span className="text-xs text-[var(--color-ink-faint)]">—</span>;
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[var(--color-surface-hover)] text-[var(--color-ink-muted)] border border-[var(--color-border)]">
      {LABEL[category]}
    </span>
  );
}
