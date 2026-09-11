import { useImperativeHandle, useRef, useState, forwardRef } from "react";
import { ChevronDown, ChevronRight, Check, Pencil, ArrowUpRight, X, Copy, Sparkles, RefreshCw, ShieldCheck } from "lucide-react";
import type { EmailDetail as EmailDetailType } from "../lib/api";
import { api } from "../lib/api";
import { CategoryPill } from "../components/CategoryPill";
import { UrgencyDot } from "../components/UrgencyDot";
import { ConfidenceBar } from "../components/ConfidenceBar";
import { Modal } from "../components/ui/Modal";
import { useToast } from "../components/ui/Toast";
import { CURRENT_USER } from "../lib/user";
import { Link } from "react-router-dom";

function extractedInfo(steps: EmailDetailType["steps"]): { customerName: string | null; orderOrAccountId: string | null } | null {
  const step = steps.find((s) => s.tool_called === "extract_customer_info" && !s.is_error);
  if (!step) return null;
  const result = step.result as Record<string, unknown>;
  return {
    customerName: (result.customer_name as string | null | undefined) ?? null,
    orderOrAccountId: (result.order_or_account_id as string | null | undefined) ?? null,
  };
}

export interface EmailDetailHandle {
  approve: () => void;
  escalate: () => void;
  openReject: () => void;
}

export const EmailDetail = forwardRef<EmailDetailHandle, {
  email: EmailDetailType;
  alreadyRead: boolean;
  onChanged: (message?: string) => void;
}>(function EmailDetail({ email, alreadyRead, onChanged }, ref) {
  const [originalExpanded, setOriginalExpanded] = useState(!alreadyRead);
  const [editText, setEditText] = useState(email.draft?.final_text ?? "");
  const [isEditing, setIsEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectPrompt, setShowRejectPrompt] = useState(false);
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const toast = useToast();
  // No reset-on-prop-change effect needed: Inbox renders this with
  // key={email.id}, so switching emails remounts the component and these
  // useState initializers run fresh — the idiomatic React way to reset
  // local state when identity changes, rather than syncing it in an effect.

  async function handleApprove() {
    setBusy(true);
    try {
      await api.approve(email.id, CURRENT_USER, isEditing ? editText : undefined);
      setShowApproveConfirm(false);
      onChanged("Response approved and sent to review log");
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    if (!rejectReason.trim()) return;
    setBusy(true);
    try {
      await api.reject(email.id, CURRENT_USER, rejectReason);
      onChanged("Draft rejected");
    } finally {
      setBusy(false);
    }
  }

  async function handleEscalate() {
    setBusy(true);
    try {
      await api.escalate(email.id, "Flagged for human review from the Inbox.");
      onChanged("Email escalated for manual handling");
    } finally {
      setBusy(false);
    }
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(email.draft?.final_text ?? "");
      toast.show("Draft copied to clipboard", "info");
    } catch {
      toast.show("Couldn't copy — try selecting the text manually", "error");
    }
  }

  const decided = email.status !== "pending";
  const extracted = extractedInfo(email.steps);

  useImperativeHandle(ref, () => ({
    approve: () => { if (!decided && !busy) setShowApproveConfirm(true); },
    escalate: () => { if (!decided && !busy) handleEscalate(); },
    openReject: () => { if (!decided && !busy) setShowRejectPrompt(true); },
  }));

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        {/* header */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <UrgencyDot urgency={email.classification?.urgency ?? null} />
            <h2 className="text-base font-semibold text-[var(--color-ink)] truncate">{email.subject}</h2>
          </div>
          <p className="text-xs text-[var(--color-ink-muted)]">{email.from_address}</p>
        </div>

        {/* original email — professional reader layout */}
        <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
          <button
            onClick={() => setOriginalExpanded((v) => !v)}
            className="w-full flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)]"
          >
            {originalExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Original email
          </button>
          {originalExpanded && (
            <div className="border-t border-[var(--color-border)]">
              <div className="px-3 py-2.5 bg-[var(--color-surface-sunken)] space-y-1 text-xs text-[var(--color-ink-muted)]">
                <div className="flex gap-2"><span className="w-14 shrink-0 text-[var(--color-ink-faint)]">From</span><span className="text-[var(--color-ink)]">{email.from_address}</span></div>
                <div className="flex gap-2"><span className="w-14 shrink-0 text-[var(--color-ink-faint)]">Subject</span><span className="text-[var(--color-ink)]">{email.subject}</span></div>
              </div>
              <div className="px-3 py-3 text-sm text-[var(--color-ink)] whitespace-pre-wrap">{email.body}</div>
            </div>
          )}
        </div>

        {/* AI analysis */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Sparkles size={13} className="text-[var(--color-ai)]" />
            <h3 className="text-xs font-semibold text-[var(--color-ink-muted)]">AI Analysis</h3>
          </div>
          {email.classification ? (
            <div className="border border-[var(--color-border)] rounded-lg p-3.5 space-y-3">
              <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm">
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)] mb-0.5">Category</p>
                  <CategoryPill category={email.classification.category} />
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)] mb-0.5">Urgency</p>
                  <span className="inline-flex items-center gap-1.5 capitalize text-[var(--color-ink)]">
                    <UrgencyDot urgency={email.classification.urgency} />
                    {email.classification.urgency}
                  </span>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)] mb-0.5">Confidence</p>
                  <ConfidenceBar value={email.classification.confidence} />
                </div>
                {extracted?.customerName && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)] mb-0.5">Customer</p>
                    <span className="text-[var(--color-ink)]">{extracted.customerName}</span>
                  </div>
                )}
                {extracted?.orderOrAccountId && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-[var(--color-ink-faint)] mb-0.5">Order / Account</p>
                    <span className="text-[var(--color-ink)] font-mono text-xs">#{extracted.orderOrAccountId}</span>
                  </div>
                )}
              </div>
              <p className="text-xs text-[var(--color-ink-muted)] pt-2 border-t border-[var(--color-border)]">
                {email.classification.reasoning}
              </p>
              <p className="text-[10px] text-[var(--color-ink-faint)] inline-flex items-center gap-1">
                <Sparkles size={10} className="text-[var(--color-ai)]" /> Analyzed by AI
              </p>
            </div>
          ) : (
            <p className="text-sm text-[var(--color-ink-faint)]">No classification recorded.</p>
          )}
        </div>

        {/* escalation reason, if escalated */}
        {email.escalation && (
          <div className="border border-[var(--color-urgent-medium)] bg-[var(--color-urgent-medium-soft)] rounded-lg p-3">
            <p className="text-xs font-semibold text-[var(--color-urgent-medium)] mb-1">Escalated</p>
            <p className="text-sm text-[var(--color-ink)]">{email.escalation.reason}</p>
          </div>
        )}

        {/* AI draft reply */}
        {email.draft && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <Sparkles size={13} className="text-[var(--color-ai)]" />
                <h3 className="text-xs font-semibold text-[var(--color-ink-muted)]">AI Draft</h3>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={handleCopy} className="inline-flex items-center gap-1 text-xs text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]">
                  <Copy size={12} /> Copy
                </button>
                <span title="Regenerating a draft isn't wired up yet — coming soon.">
                  <button disabled className="inline-flex items-center gap-1 text-xs text-[var(--color-ink-faint)] cursor-not-allowed">
                    <RefreshCw size={12} /> Regenerate
                  </button>
                </span>
                {!decided && !isEditing && (
                  <button
                    onClick={() => { setIsEditing(true); setTimeout(() => textareaRef.current?.focus(), 0); }}
                    className="inline-flex items-center gap-1 text-xs text-[var(--color-accent)] hover:underline"
                  >
                    <Pencil size={12} /> Edit
                  </button>
                )}
              </div>
            </div>
            <p className="text-xs text-[var(--color-ink-faint)] mb-2">AI-generated response — review before sending.</p>
            <textarea
              ref={textareaRef}
              value={isEditing ? editText : email.draft.final_text}
              onChange={(e) => setEditText(e.target.value)}
              readOnly={!isEditing || decided}
              rows={7}
              className={`w-full rounded-lg border px-3 py-2.5 text-sm resize-y leading-relaxed ${
                isEditing && !decided
                  ? "border-[var(--color-accent)] bg-[var(--color-surface)]"
                  : "border-[var(--color-border)] bg-[var(--color-surface-sunken)]"
              }`}
            />
            {email.draft.sources_used.length > 0 && (
              <div className="mt-2">
                <p className="text-xs text-[var(--color-ink-muted)] mb-1">Sources used</p>
                <div className="flex flex-wrap gap-1.5">
                  {email.draft.sources_used.map((id) => (
                    <span key={id} className="px-2 py-0.5 rounded text-xs bg-[var(--color-surface-hover)] border border-[var(--color-border)] text-[var(--color-ink-muted)]">
                      {id}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {decided && email.draft.approver && (
              <p className="mt-2 text-xs text-[var(--color-ink-faint)]">
                {email.draft.status === "approved" ? "Approved" : "Rejected"} by {email.draft.approver}
              </p>
            )}
          </div>
        )}

        <Link
          to={`/runs/${email.id}`}
          className="inline-flex items-center gap-1 text-xs text-[var(--color-accent)] hover:underline"
        >
          View full agent run <ArrowUpRight size={12} />
        </Link>

        {showRejectPrompt && !decided && (
          <div className="border border-[var(--color-border)] rounded-lg p-3 space-y-2">
            <label className="text-xs font-medium text-[var(--color-ink-muted)]" htmlFor="reject-reason">
              Why are you rejecting this draft?
            </label>
            <textarea
              id="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={2}
              autoFocus
              className="w-full rounded-lg border border-[var(--color-border)] px-2 py-1.5 text-sm"
              placeholder="e.g. wrong tone, missing information..."
            />
            <div className="flex gap-2">
              <button
                onClick={handleReject}
                disabled={busy || !rejectReason.trim()}
                className="px-3 py-1 rounded-md text-xs font-medium bg-[var(--color-urgent-high)] text-white disabled:opacity-40"
              >
                Confirm reject
              </button>
              <button onClick={() => setShowRejectPrompt(false)} className="px-3 py-1 rounded-md text-xs text-[var(--color-ink-muted)]">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* sticky action bar */}
      {email.draft && !decided && (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-3 space-y-2">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowApproveConfirm(true)}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 shadow-sm"
            >
              <Check size={14} /> Approve & Send <kbd className="ml-1 text-[10px] opacity-70">A</kbd>
            </button>
            <button
              onClick={handleEscalate}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium text-[var(--color-ink-muted)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
            >
              Escalate <kbd className="ml-1 text-[10px] opacity-70">E</kbd>
            </button>
            <button
              onClick={() => setShowRejectPrompt(true)}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium text-[var(--color-urgent-high)] hover:bg-[var(--color-urgent-high-soft)] disabled:opacity-50"
            >
              <X size={14} /> Reject <kbd className="ml-1 text-[10px] opacity-70">R</kbd>
            </button>
          </div>
          <p className="flex items-center gap-1.5 text-[11px] text-[var(--color-ink-faint)]">
            <ShieldCheck size={12} /> Human approval required before anything is sent
          </p>
        </div>
      )}

      {showApproveConfirm && (
        <Modal title="Ready to send?" onClose={() => !busy && setShowApproveConfirm(false)}>
          <p className="text-sm text-[var(--color-ink-muted)] mb-1">This response will be sent to:</p>
          <p className="text-sm font-medium text-[var(--color-ink)] mb-3">{email.from_address}</p>
          <div className="border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-sunken)] px-3 py-2.5 max-h-40 overflow-y-auto text-sm text-[var(--color-ink)] whitespace-pre-wrap mb-4">
            {isEditing ? editText : email.draft?.final_text}
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setShowApproveConfirm(false)}
              disabled={busy}
              className="px-3 py-1.5 rounded-md text-sm text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleApprove}
              disabled={busy}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
            >
              <Check size={14} /> Approve & Send
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
});
