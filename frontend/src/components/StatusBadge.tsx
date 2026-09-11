import type { EmailStatus } from "../lib/api";

const STYLE: Record<EmailStatus, string> = {
  pending: "bg-[var(--color-surface-hover)] text-[var(--color-ink-muted)]",
  approved: "bg-[var(--color-urgent-low-soft)] text-[var(--color-urgent-low)]",
  escalated: "bg-[var(--color-urgent-medium-soft)] text-[var(--color-urgent-medium)]",
  rejected: "bg-[var(--color-urgent-high-soft)] text-[var(--color-urgent-high)]",
};

const LABEL: Record<EmailStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  escalated: "Escalated",
  rejected: "Rejected",
};

export function StatusBadge({ status }: { status: EmailStatus }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STYLE[status]}`}>
      {LABEL[status]}
    </span>
  );
}
