import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Inbox, ListTree, Settings as SettingsIcon, ChevronsLeft, ChevronsRight, Mail, Sheet, Sparkles } from "lucide-react";
import { useIntegrationsStatus } from "../lib/useIntegrationsStatus";
import { CURRENT_USER } from "../lib/user";

const NAV = [
  { to: "/", label: "Review Queue", icon: Inbox, end: true },
  { to: "/runs", label: "Runs", icon: ListTree, end: false },
  { to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
];

function StatusDot({ ok }: { ok: boolean | null }) {
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
        ok === null ? "bg-[var(--color-border-strong)]" : ok ? "bg-[var(--color-urgent-low)]" : "bg-[var(--color-ink-faint)]"
      }`}
    />
  );
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("sidebar-collapsed") === "1";
    } catch {
      return false;
    }
  });
  const status = useIntegrationsStatus();

  function toggle() {
    setCollapsed((v) => {
      const next = !v;
      try { localStorage.setItem("sidebar-collapsed", next ? "1" : "0"); } catch { /* per-viewer convenience only */ }
      return next;
    });
  }

  return (
    <aside
      className={`flex flex-col h-screen shrink-0 border-r border-[var(--color-border)] bg-[var(--color-surface)] transition-[width] duration-150 ${
        collapsed ? "w-14" : "w-56"
      }`}
    >
      <div className={`flex items-center h-12 shrink-0 border-b border-[var(--color-border)] ${collapsed ? "justify-center" : "px-4"}`}>
        <Link to="/" className="flex items-center gap-2 min-w-0">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-[var(--color-accent)] text-white shrink-0">
            <Sparkles size={13} />
          </span>
          {!collapsed && <span className="text-sm font-semibold text-[var(--color-ink)] truncate">Support Triage</span>}
        </Link>
      </div>

      <nav className="flex-1 py-3 px-2 overflow-y-auto">
        <div className="space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-md text-sm font-medium px-2.5 py-1.5 transition-colors ${collapsed ? "justify-center" : ""} ${
                  isActive
                    ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                    : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)]"
                }`
              }
            >
              <Icon size={16} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </div>

        {!collapsed && (
          <p className="px-2.5 pt-4 pb-1 text-[10px] font-semibold tracking-wide uppercase text-[var(--color-ink-faint)]">System</p>
        )}
        <div className={`space-y-0.5 ${collapsed ? "pt-4" : ""}`}>
          <div
            className={`flex items-center gap-2.5 px-2.5 py-1.5 text-xs text-[var(--color-ink-muted)] ${collapsed ? "justify-center" : ""}`}
            title={collapsed ? "Gmail" : undefined}
          >
            <Mail size={14} className="shrink-0 text-[var(--color-ink-faint)]" />
            {!collapsed && <span className="flex-1 truncate">Gmail</span>}
            <StatusDot ok={status ? status.gmail_connected : null} />
          </div>
          <div
            className={`flex items-center gap-2.5 px-2.5 py-1.5 text-xs text-[var(--color-ink-muted)] ${collapsed ? "justify-center" : ""}`}
            title={collapsed ? "Google Sheets" : undefined}
          >
            <Sheet size={14} className="shrink-0 text-[var(--color-ink-faint)]" />
            {!collapsed && <span className="flex-1 truncate">Google Sheets</span>}
            <StatusDot ok={status ? status.sheets_connected : null} />
          </div>
          <div
            className={`flex items-center gap-2.5 px-2.5 py-1.5 text-xs text-[var(--color-ink-muted)] ${collapsed ? "justify-center" : ""}`}
            title={collapsed ? `AI Agent — ${status?.ai_mode ?? "…"}` : undefined}
          >
            <Sparkles size={14} className="shrink-0 text-[var(--color-ink-faint)]" />
            {!collapsed && <span className="flex-1 truncate">AI Agent</span>}
            {!collapsed && status && (
              <span
                className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                  status.ai_mode === "claude"
                    ? "bg-[var(--color-ai-soft)] text-[var(--color-ai)]"
                    : "bg-[var(--color-surface-hover)] text-[var(--color-ink-faint)]"
                }`}
              >
                {status.ai_mode === "claude" ? "Claude" : "Fake"}
              </span>
            )}
          </div>
        </div>
      </nav>

      <div className="shrink-0 border-t border-[var(--color-border)] p-2 space-y-1">
        <div className={`flex items-center gap-2 px-1 py-1 ${collapsed ? "justify-center" : ""}`} title={collapsed ? CURRENT_USER : undefined}>
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[var(--color-accent-soft)] text-[var(--color-accent)] text-[11px] font-semibold shrink-0">
            {CURRENT_USER[0]?.toUpperCase()}
          </span>
          {!collapsed && <span className="text-xs text-[var(--color-ink-muted)] truncate">{CURRENT_USER}</span>}
        </div>
        <button
          onClick={toggle}
          className={`w-full flex items-center gap-2 rounded-md text-xs text-[var(--color-ink-faint)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink-muted)] px-2.5 py-1.5 ${collapsed ? "justify-center" : ""}`}
        >
          {collapsed ? <ChevronsRight size={14} /> : (<><ChevronsLeft size={14} /> Collapse</>)}
        </button>
      </div>
    </aside>
  );
}
