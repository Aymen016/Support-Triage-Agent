// Typed client for the Support Triage Agent API (see api/main.py).
// Base URL configurable via VITE_API_BASE — defaults to the local dev server.

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export type Category = "bug_report" | "billing" | "how_to" | "sales" | "spam" | "other";
export type Urgency = "low" | "medium" | "high";
export type EmailStatus = "pending" | "approved" | "escalated" | "rejected";

export interface EmailSummary {
  id: string;
  from_address: string;
  subject: string;
  status: EmailStatus;
  created_at: string;
  category: Category | null;
  urgency: Urgency | null;
  confidence: number | null;
}

export interface Classification {
  category: Category;
  urgency: Urgency;
  confidence: number;
  reasoning: string;
}

export interface Draft {
  draft_text: string;
  edited_text: string | null;
  final_text: string;
  sources_used: string[];
  status: "pending" | "approved" | "rejected";
  approver: string | null;
  decided_at: string | null;
}

export interface Escalation {
  reason: string;
  priority: Urgency;
  resolved: boolean;
}

export interface AgentStep {
  step_number: number;
  tool_called: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
  is_error: boolean;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface EmailDetail {
  id: string;
  from_address: string;
  subject: string;
  body: string;
  thread_id: string | null;
  status: EmailStatus;
  created_at: string;
  classification: Classification | null;
  draft: Draft | null;
  escalation: Escalation | null;
  steps: AgentStep[];
}

export interface Settings {
  confidence_threshold: number;
  auto_send_enabled: boolean;
  tone_instructions: string;
  category_notes: string;
}

export interface RunSummary {
  processed: number;
  drafted: number;
  escalated: number;
  skipped_already_seen: number;
  used_fake_llm: boolean;
  email_source: "fixtures" | "gmail";
}

export interface IntegrationsStatus {
  gmail_connected: boolean;
  sheets_connected: boolean;
  ai_mode: "claude" | "fake";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  listEmails: (status?: EmailStatus) =>
    request<EmailSummary[]>(`/emails${status ? `?status=${status}` : ""}`),

  getEmail: (id: string) => request<EmailDetail>(`/emails/${id}`),

  getRunSteps: (id: string) => request<AgentStep[]>(`/runs/${id}`),

  approve: (id: string, approver: string, editedText?: string) =>
    request<EmailDetail>(`/emails/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approver, edited_text: editedText }),
    }),

  reject: (id: string, approver: string, reason: string) =>
    request<EmailDetail>(`/emails/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ approver, reason }),
    }),

  escalate: (id: string, reason: string) =>
    request<EmailDetail>(`/emails/${id}/escalate`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  getSettings: () => request<Settings>("/settings"),

  updateSettings: (patch: Partial<Settings>) =>
    request<Settings>("/settings", { method: "PUT", body: JSON.stringify(patch) }),

  run: () => request<RunSummary>("/run", { method: "POST" }),

  runStreamUrl: () => `${API_BASE}/run/stream`,

  getIntegrationsStatus: () => request<IntegrationsStatus>("/integrations/status"),
};
