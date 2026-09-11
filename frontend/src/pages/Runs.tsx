import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Check, AlertTriangle, ListTree, Play } from "lucide-react";
import { api, type AgentStep, type EmailSummary } from "../lib/api";
import { estimateCostUsd, formatCostUsd } from "../lib/pricing";
import { StatusBadge } from "../components/StatusBadge";
import { UrgencyDot } from "../components/UrgencyDot";

function totalLatency(steps: AgentStep[]): number {
  return steps.reduce((sum, s) => sum + s.latency_ms, 0);
}
function totalTokens(steps: AgentStep[]): { input: number; output: number } {
  return steps.reduce(
    (acc, s) => ({ input: acc.input + (s.input_tokens ?? 0), output: acc.output + (s.output_tokens ?? 0) }),
    { input: 0, output: 0 },
  );
}
function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function StepRow({ step }: { step: AgentStep }) {
  const [expanded, setExpanded] = useState(false);
  const summary = summarizeResult(step);

  return (
    <li className="border-b border-[var(--color-border)] last:border-b-0">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-[var(--color-surface-hover)]"
      >
        {expanded ? <ChevronDown size={13} className="text-[var(--color-ink-faint)]" /> : <ChevronRight size={13} className="text-[var(--color-ink-faint)]" />}
        <span className="text-xs text-[var(--color-ink-faint)] tabular w-12">Step {step.step_number}</span>
        <span className="text-sm font-mono text-[var(--color-ink)] w-44 truncate">{step.tool_called}</span>
        <span className="tabular text-xs text-[var(--color-ink-muted)] w-14">{formatMs(step.latency_ms)}</span>
        {step.is_error ? (
          <AlertTriangle size={14} className="text-[var(--color-urgent-high)] shrink-0" />
        ) : (
          <Check size={14} className="text-[var(--color-urgent-low)] shrink-0" />
        )}
        <span className={`text-xs truncate ${step.is_error ? "text-[var(--color-urgent-high)]" : "text-[var(--color-ink-muted)]"}`}>
          {summary}
        </span>
      </button>
      {expanded && (
        <div className="px-3 pb-3 pl-16 space-y-2">
          <div>
            <p className="text-[10px] font-semibold uppercase text-[var(--color-ink-faint)] mb-1">Arguments</p>
            <pre className="text-xs bg-[var(--color-surface-hover)] rounded p-2 overflow-x-auto">{JSON.stringify(step.arguments, null, 2)}</pre>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase text-[var(--color-ink-faint)] mb-1">Result</p>
            <pre className={`text-xs rounded p-2 overflow-x-auto ${step.is_error ? "bg-[var(--color-urgent-high-soft)]" : "bg-[var(--color-surface-hover)]"}`}>
              {JSON.stringify(step.result, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </li>
  );
}

function summarizeResult(step: AgentStep): string {
  const r = step.result as Record<string, unknown>;
  if (step.is_error) return String(r.message ?? r.error ?? r.detail ?? "error");
  switch (step.tool_called) {
    case "classify_email":
      return `${r.category} / ${r.urgency} / ${Number(r.confidence).toFixed(2)}`;
    case "extract_customer_info":
      return r.customer_name ? `name: ${r.customer_name}` : "no identifiable fields";
    case "search_knowledge_base":
      return `${(r.hits as unknown[] | undefined)?.length ?? 0} articles found`;
    case "draft_reply":
      return `${String(r.draft_text ?? "").length} chars drafted`;
    case "escalate_to_human":
      return `reason: ${r.reason}`;
    default:
      return "";
  }
}

export function Runs() {
  const { emailId } = useParams();
  const navigate = useNavigate();
  const [emails, setEmails] = useState<EmailSummary[]>([]);
  const [steps, setSteps] = useState<AgentStep[] | null>(null);
  const [selectedSubject, setSelectedSubject] = useState<string | null>(null);

  useEffect(() => {
    api.listEmails().then(setEmails);
  }, []);

  useEffect(() => {
    if (!emailId) { setSteps(null); return; }
    api.getRunSteps(emailId).then(setSteps);
    const match = emails.find((e) => e.id === emailId);
    if (match) setSelectedSubject(match.subject);
  }, [emailId, emails]);

  const stats = useMemo(() => {
    if (!steps) return null;
    const tokens = totalTokens(steps);
    return {
      latencyMs: totalLatency(steps),
      tokens,
      cost: estimateCostUsd(tokens.input, tokens.output),
      errorCount: steps.filter((s) => s.is_error).length,
    };
  }, [steps]);

  return (
    <div className="flex h-[calc(100vh-3rem)]">
      {/* run list */}
      <div className="w-2/5 border-r border-[var(--color-border)] overflow-y-auto">
        {emails.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6 gap-3">
            <ListTree size={22} className="text-[var(--color-ink-faint)]" />
            <p className="text-sm text-[var(--color-ink-muted)]">No runs yet.</p>
            <button
              onClick={() => navigate("/")}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)]"
            >
              <Play size={13} /> Go run the agent
            </button>
          </div>
        ) : (
          <ul>
            {emails.map((e) => (
              <li key={e.id}>
                <button
                  onClick={() => navigate(`/runs/${e.id}`)}
                  className={`w-full text-left px-4 py-2.5 border-b border-[var(--color-border)] flex items-center gap-2.5 ${
                    emailId === e.id ? "bg-[var(--color-accent-soft)]" : "hover:bg-[var(--color-surface-hover)]"
                  }`}
                >
                  <UrgencyDot urgency={e.urgency} />
                  <span className="flex-1 min-w-0 text-sm text-[var(--color-ink)] truncate">{e.subject}</span>
                  <StatusBadge status={e.status} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* timeline */}
      <div className="w-3/5 overflow-y-auto">
        {!emailId || !steps ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-[var(--color-ink-faint)]">
            <ListTree size={22} />
            <p className="text-sm">Select a run to see its step-by-step trail</p>
          </div>
        ) : (
          <div className="p-5">
            <h2 className="text-sm font-semibold text-[var(--color-ink)] mb-3 truncate">{selectedSubject}</h2>
            <ul className="border border-[var(--color-border)] rounded overflow-hidden">
              {steps.map((s) => <StepRow key={s.step_number} step={s} />)}
            </ul>
            {stats && (
              <div className="mt-3 flex items-center gap-4 px-3 py-2 border border-[var(--color-border)] rounded text-xs text-[var(--color-ink-muted)] tabular">
                <span>total {formatMs(stats.latencyMs)}</span>
                <span>·</span>
                <span>{stats.tokens.input + stats.tokens.output} tokens</span>
                <span>·</span>
                <span title="Estimated at Claude Sonnet 5 rates — see lib/pricing.ts">{formatCostUsd(stats.cost)} est.</span>
                {stats.errorCount > 0 && (
                  <>
                    <span>·</span>
                    <span className="text-[var(--color-urgent-high)]">{stats.errorCount} error{stats.errorCount > 1 ? "s" : ""}</span>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
