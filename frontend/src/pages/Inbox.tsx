import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, Play, Loader2, Inbox as InboxIcon, MousePointerClick, Filter, ChevronDown } from "lucide-react";
import { api, type EmailDetail as EmailDetailType, type EmailSummary, type Category } from "../lib/api";
import { useAgentRun } from "../lib/useAgentRun";
import { useToast } from "../components/ui/Toast";
import { EmailListItemSkeleton, EmailDetailSkeleton } from "../components/ui/Skeleton";
import { UrgencyDot } from "../components/UrgencyDot";
import { CategoryPill } from "../components/CategoryPill";
import { ConfidenceBar } from "../components/ConfidenceBar";
import { StatusBadge } from "../components/StatusBadge";
import { RelativeTime } from "../components/RelativeTime";
import { EmailDetail, type EmailDetailHandle } from "./EmailDetail";

type FilterKey = "all" | "pending" | "escalated" | "approved" | "rejected" | "high";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "pending", label: "Pending" },
  { key: "escalated", label: "Escalated" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "high", label: "High urgency" },
];

const ALL_CATEGORIES: Category[] = ["bug_report", "billing", "how_to", "sales", "spam", "other"];
const CATEGORY_LABEL: Record<Category, string> = {
  bug_report: "Bug report", billing: "Billing", how_to: "How-to", sales: "Sales", spam: "Spam", other: "Other",
};

export function Inbox() {
  const [emails, setEmails] = useState<EmailSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>("pending");
  const [categoryFilter, setCategoryFilter] = useState<Set<Category>>(new Set());
  const [categoryMenuOpen, setCategoryMenuOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [detail, setDetail] = useState<EmailDetailType | null>(null);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const [params, setParams] = useSearchParams();
  const detailRef = useRef<EmailDetailHandle>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const refresh = useCallback(async () => {
    const list = await api.listEmails();
    setEmails(list);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const { progress, start } = useAgentRun(async () => {
    await refresh();
    toast.show("Agent run complete", "success");
  });

  const filtered = useMemo(() => {
    let rows = emails;
    if (filter === "pending") rows = rows.filter((e) => e.status === "pending");
    if (filter === "escalated") rows = rows.filter((e) => e.status === "escalated");
    if (filter === "approved") rows = rows.filter((e) => e.status === "approved");
    if (filter === "rejected") rows = rows.filter((e) => e.status === "rejected");
    if (filter === "high") rows = rows.filter((e) => e.urgency === "high");
    if (categoryFilter.size > 0) rows = rows.filter((e) => e.category && categoryFilter.has(e.category));
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter((e) => e.subject.toLowerCase().includes(q) || e.from_address.toLowerCase().includes(q));
    }
    return rows;
  }, [emails, filter, categoryFilter, search]);

  const selectedId = params.get("email");
  // Derived, not stored: while a newly-selected email's detail is still in
  // flight, `detail` briefly still holds the PREVIOUS email's data — without
  // this check the panel would flash the wrong email's content for a beat.
  const isLoadingDetail = Boolean(selectedId) && (!detail || detail.id !== selectedId);

  const selectEmail = useCallback(async (id: string) => {
    setParams((p) => { p.set("email", id); return p; }, { replace: true });
    const d = await api.getEmail(id);
    setDetail(d);
    setReadIds((prev) => new Set(prev).add(id));
  }, [setParams]);

  useEffect(() => {
    if (selectedId && (!detail || detail.id !== selectedId)) {
      selectEmail(selectedId);
    }
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  // keyboard: Cmd/Ctrl+K focuses search, J/K move selection, A/E/R delegate
  // to the detail panel's action handles
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "TEXTAREA" || tag === "INPUT") return; // don't hijack typing

      if (e.key === "j" || e.key === "k") {
        const idx = filtered.findIndex((e) => e.id === selectedId);
        const next = e.key === "j" ? Math.min(idx + 1, filtered.length - 1) : Math.max(idx - 1, 0);
        if (filtered[next]) selectEmail(filtered[next].id);
      } else if (e.key === "a") {
        detailRef.current?.approve();
      } else if (e.key === "e") {
        detailRef.current?.escalate();
      } else if (e.key === "r") {
        detailRef.current?.openReject();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filtered, selectedId, selectEmail]);

  async function handleChanged(message?: string) {
    await refresh();
    if (selectedId) {
      const d = await api.getEmail(selectedId);
      setDetail(d);
    }
    if (message) toast.show(message, "success");
  }

  const handledCount = emails.filter((e) => e.status !== "pending").length;

  function toggleCategory(c: Category) {
    setCategoryFilter((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c); else next.add(c);
      return next;
    });
  }

  return (
    <div className="flex flex-col h-full">
      {/* toolbar */}
      <div className="flex items-center gap-2 px-5 py-2.5 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex-wrap">
        <div className="flex items-center gap-1 shrink-0">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                filter === f.key
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                  : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="relative shrink-0">
          <button
            onClick={() => setCategoryMenuOpen((v) => !v)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-colors ${
              categoryFilter.size > 0
                ? "border-transparent text-[var(--color-accent)] bg-[var(--color-accent-soft)]"
                : "border-[var(--color-border)] text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            <Filter size={12} />
            Category{categoryFilter.size > 0 ? ` (${categoryFilter.size})` : ""}
            <ChevronDown size={12} />
          </button>
          {categoryMenuOpen && (
            <>
              <div className="fixed inset-0 z-30" onClick={() => setCategoryMenuOpen(false)} />
              <div className="absolute left-0 mt-1.5 w-44 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg p-1.5 z-40">
                {ALL_CATEGORIES.map((c) => (
                  <label
                    key={c}
                    className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[var(--color-surface-hover)] text-xs text-[var(--color-ink)] cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={categoryFilter.has(c)}
                      onChange={() => toggleCategory(c)}
                      className="accent-[var(--color-accent)]"
                    />
                    {CATEGORY_LABEL[c]}
                  </label>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-1 max-w-xs px-2.5 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] shrink-0">
          <Search size={13} className="text-[var(--color-ink-faint)]" />
          <input
            ref={searchRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search sender or subject"
            className="bg-transparent text-xs outline-none flex-1 min-w-0 placeholder:text-[var(--color-ink-faint)]"
          />
          <kbd className="text-[10px] text-[var(--color-ink-faint)] border border-[var(--color-border)] rounded px-1 shrink-0">⌘K</kbd>
        </div>
        <div className="flex-1" />
        <button
          onClick={start}
          disabled={progress.isRunning}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-60 shadow-sm shrink-0"
        >
          {progress.isRunning ? (
            <>
              <Loader2 size={13} className="animate-spin" />
              <span className="animate-agent-pulse">
                {progress.currentEmailSubject ? `Working: ${progress.currentEmailSubject.slice(0, 24)}…` : "Running…"}
              </span>
            </>
          ) : (
            <>
              <Play size={13} /> Run agent on new emails
            </>
          )}
        </button>
      </div>

      {/* split layout */}
      <div className="flex flex-1 min-h-0">
        {/* list ~40% */}
        <div className="w-2/5 border-r border-[var(--color-border)] overflow-y-auto">
          {loading ? (
            <div>{Array.from({ length: 8 }).map((_, i) => <EmailListItemSkeleton key={i} />)}</div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-6 gap-2">
              <InboxIcon size={22} className="text-[var(--color-ink-faint)]" />
              <p className="text-sm text-[var(--color-ink-muted)]">
                {emails.length === 0 ? "No emails yet — run the agent to process new ones." : "You're all caught up."}
              </p>
              {emails.length > 0 && (
                <p className="text-xs text-[var(--color-ink-faint)]">{handledCount} handled so far.</p>
              )}
            </div>
          ) : (
            <ul>
              {filtered.map((e) => {
                const isRead = readIds.has(e.id);
                return (
                  <li key={e.id}>
                    <button
                      onClick={() => selectEmail(e.id)}
                      className={`w-full text-left px-4 py-2.5 border-b border-[var(--color-border)] flex items-center gap-2.5 transition-colors ${
                        selectedId === e.id ? "bg-[var(--color-accent-soft)]" : "hover:bg-[var(--color-surface-hover)]"
                      }`}
                    >
                      <UrgencyDot urgency={e.urgency} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span
                            className={`text-sm truncate ${
                              isRead ? "font-medium text-[var(--color-ink-muted)]" : "font-semibold text-[var(--color-ink)]"
                            }`}
                          >
                            {e.from_address}
                          </span>
                          <RelativeTime iso={e.created_at} />
                        </div>
                        <div className="flex items-center justify-between gap-2 mt-0.5">
                          <span className={`text-xs truncate ${isRead ? "text-[var(--color-ink-faint)]" : "text-[var(--color-ink-muted)]"}`}>
                            {e.subject}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <CategoryPill category={e.category} />
                          <ConfidenceBar value={e.confidence} showLabel={false} />
                          <StatusBadge status={e.status} />
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* detail ~60% */}
        <div className="w-3/5">
          {isLoadingDetail ? (
            <EmailDetailSkeleton />
          ) : detail ? (
            <EmailDetail key={detail.id} ref={detailRef} email={detail} alreadyRead={readIds.has(detail.id)} onChanged={handleChanged} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center px-6 gap-2 text-[var(--color-ink-faint)]">
              <MousePointerClick size={22} />
              <p className="text-sm">Select an email to review</p>
              <p className="text-xs tabular">J/K navigate · A approve · E escalate · R reject</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
