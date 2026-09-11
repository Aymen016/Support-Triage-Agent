import { useState } from "react";
import { useLocation } from "react-router-dom";
import { Bell, Moon, Sun } from "lucide-react";
import { useIntegrationsStatus } from "../lib/useIntegrationsStatus";
import { useTheme } from "../lib/useTheme";
import { CURRENT_USER } from "../lib/user";

const TITLES: [string, string][] = [
  ["/settings", "Settings"],
  ["/runs", "Runs"],
  ["/", "Review Queue"],
];

function pageTitle(pathname: string): string {
  for (const [prefix, title] of TITLES) {
    if (pathname === prefix || (prefix !== "/" && pathname.startsWith(prefix))) return title;
  }
  return "Support Triage";
}

export function TopBar() {
  const location = useLocation();
  const status = useIntegrationsStatus();
  const [theme, toggleTheme] = useTheme();
  const [notifOpen, setNotifOpen] = useState(false);

  return (
    <header className="h-12 shrink-0 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center gap-3 px-5">
      <h1 className="text-sm font-semibold text-[var(--color-ink)]">{pageTitle(location.pathname)}</h1>
      <div className="flex-1" />

      <span
        className={`hidden sm:inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border ${
          status?.gmail_connected
            ? "border-transparent bg-[var(--color-urgent-low-soft)] text-[var(--color-urgent-low)]"
            : "border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-ink-muted)]"
        }`}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${status?.gmail_connected ? "bg-[var(--color-urgent-low)]" : "bg-[var(--color-ink-faint)]"}`} />
        {status ? (status.gmail_connected ? "Gmail Connected" : "Gmail Not Connected") : "…"}
      </span>

      <button
        onClick={toggleTheme}
        aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        className="p-1.5 rounded-md text-[var(--color-ink-faint)] hover:text-[var(--color-ink)] hover:bg-[var(--color-surface-hover)]"
      >
        {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
      </button>

      <div className="relative">
        <button
          onClick={() => setNotifOpen((v) => !v)}
          aria-label="Notifications"
          className="p-1.5 rounded-md text-[var(--color-ink-faint)] hover:text-[var(--color-ink)] hover:bg-[var(--color-surface-hover)]"
        >
          <Bell size={16} />
        </button>
        {notifOpen && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setNotifOpen(false)} />
            <div className="absolute right-0 mt-2 w-64 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg p-4 text-center z-40">
              <p className="text-xs text-[var(--color-ink-muted)]">No notifications yet.</p>
            </div>
          </>
        )}
      </div>

      <span
        className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[var(--color-accent-soft)] text-[var(--color-accent)] text-[11px] font-semibold"
        title={CURRENT_USER}
      >
        {CURRENT_USER[0]?.toUpperCase()}
      </span>
    </header>
  );
}
