import { useEffect, useState } from "react";
import { Check, TriangleAlert, Mail, Sheet } from "lucide-react";
import { api, type Settings as SettingsType } from "../lib/api";

const CATEGORY_DESCRIPTIONS: [string, string][] = [
  ["Bug report", "Something is broken, an error occurred, a feature isn't working."],
  ["Billing", "Charges, invoices, refunds, subscriptions, payment problems."],
  ["How-to", "The customer needs instructions or guidance using the product."],
  ["Sales", "A pre-sales or purchasing enquiry, not an existing customer's issue."],
  ["Spam", "Automated noise, marketing, phishing, irrelevant mail."],
  ["Other", "Doesn't fit the above, or genuinely unclear."],
];

export function Settings() {
  const [settings, setSettings] = useState<SettingsType | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => { api.getSettings().then(setSettings); }, []);

  async function save(patch: Partial<SettingsType>) {
    setSaving(true);
    try {
      const updated = await api.updateSettings(patch);
      setSettings(updated);
      setSavedAt(Date.now());
    } finally {
      setSaving(false);
    }
  }

  if (!settings) return <div className="p-6 text-xs text-[var(--color-ink-faint)]">Loading…</div>;

  return (
    <div className="max-w-2xl px-6 py-6 space-y-8 overflow-y-auto h-[calc(100vh-3rem)]">
      <div className="flex items-center justify-between">
        <h1 className="text-base font-semibold text-[var(--color-ink)]">Settings</h1>
        {savedAt && !saving && (
          <span className="inline-flex items-center gap-1 text-xs text-[var(--color-urgent-low)]">
            <Check size={13} /> Saved
          </span>
        )}
      </div>

      {/* Category definitions & routing rules */}
      <section>
        <h2 className="text-sm font-semibold text-[var(--color-ink)] mb-1">Category definitions & routing rules</h2>
        <p className="text-xs text-[var(--color-ink-muted)] mb-3">
          How the agent classifies incoming emails. The six categories below are fixed; use the notes field to
          steer edge cases without waiting on a code change.
        </p>
        <div className="border border-[var(--color-border)] rounded divide-y divide-[var(--color-border)] mb-3">
          {CATEGORY_DESCRIPTIONS.map(([name, desc]) => (
            <div key={name} className="flex gap-3 px-3 py-2 text-sm">
              <span className="w-24 shrink-0 font-medium text-[var(--color-ink)]">{name}</span>
              <span className="text-[var(--color-ink-muted)]">{desc}</span>
            </div>
          ))}
        </div>
        <label className="text-xs font-medium text-[var(--color-ink-muted)]" htmlFor="category-notes">
          Additional routing notes
        </label>
        <textarea
          id="category-notes"
          rows={3}
          defaultValue={settings.category_notes}
          onBlur={(e) => save({ category_notes: e.target.value })}
          placeholder="e.g. Treat anything mentioning 'lawsuit' or 'attorney' as billing/high, regardless of wording."
          className="mt-1 w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm"
        />
        <p className="text-xs text-[var(--color-ink-faint)] mt-1">
          Fed directly into the classifier's instructions — takes effect on the next run.
        </p>
      </section>

      {/* Confidence threshold */}
      <section>
        <h2 className="text-sm font-semibold text-[var(--color-ink)] mb-1">Confidence threshold</h2>
        <p className="text-xs text-[var(--color-ink-muted)] mb-3">
          Classifications below this confidence get escalated to a human automatically instead of drafted.
          One global threshold today — per-category thresholds are a natural next step.
        </p>
        <div className="flex items-center gap-3">
          <input
            type="range" min={0} max={1} step={0.05}
            value={settings.confidence_threshold}
            onChange={(e) => setSettings({ ...settings, confidence_threshold: Number(e.target.value) })}
            onMouseUp={(e) => save({ confidence_threshold: Number((e.target as HTMLInputElement).value) })}
            onKeyUp={(e) => save({ confidence_threshold: Number((e.target as HTMLInputElement).value) })}
            className="w-48"
          />
          <span className="tabular text-sm font-medium text-[var(--color-ink)] w-10">
            {Math.round(settings.confidence_threshold * 100)}%
          </span>
        </div>
      </section>

      {/* Auto-send */}
      <section>
        <h2 className="text-sm font-semibold text-[var(--color-ink)] mb-1">Auto-send</h2>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={settings.auto_send_enabled}
            onChange={(e) => save({ auto_send_enabled: e.target.checked })}
            className="w-4 h-4 accent-[var(--color-accent)]"
          />
          <span className="text-sm text-[var(--color-ink)]">
            Automatically send high-confidence, low-risk replies without human approval
          </span>
        </label>
        <div className="mt-2 flex items-start gap-2 px-3 py-2 rounded border border-[var(--color-urgent-medium)] bg-[var(--color-urgent-medium-soft)]">
          <TriangleAlert size={14} className="text-[var(--color-urgent-medium)] mt-0.5 shrink-0" />
          <p className="text-xs text-[var(--color-ink)]">
            Off by default, and every reply still goes through the review queue today regardless of this
            setting — there's no real send channel wired up yet (that's Phase 6, Gmail send). This flag is
            stored for when that exists, so turning it on right now changes nothing.
          </p>
        </div>
      </section>

      {/* Tone */}
      <section>
        <h2 className="text-sm font-semibold text-[var(--color-ink)] mb-1">Tone & voice for drafts</h2>
        <p className="text-xs text-[var(--color-ink-muted)] mb-2">Edit freely — no engineering needed.</p>
        <textarea
          rows={3}
          defaultValue={settings.tone_instructions}
          onBlur={(e) => save({ tone_instructions: e.target.value })}
          className="w-full rounded border border-[var(--color-border)] px-3 py-2 text-sm"
        />
      </section>

      {/* Integrations */}
      <section>
        <h2 className="text-sm font-semibold text-[var(--color-ink)] mb-1">Connected integrations</h2>
        <div className="border border-[var(--color-border)] rounded divide-y divide-[var(--color-border)]">
          <div className="flex items-center gap-3 px-3 py-2.5">
            <Mail size={16} className="text-[var(--color-ink-faint)]" />
            <span className="flex-1 text-sm text-[var(--color-ink)]">Gmail</span>
            <span className="text-xs px-2 py-0.5 rounded bg-[var(--color-surface-hover)] text-[var(--color-ink-muted)]">Not connected</span>
          </div>
          <div className="flex items-center gap-3 px-3 py-2.5">
            <Sheet size={16} className="text-[var(--color-ink-faint)]" />
            <span className="flex-1 text-sm text-[var(--color-ink)]">Google Sheets</span>
            <span className="text-xs px-2 py-0.5 rounded bg-[var(--color-surface-hover)] text-[var(--color-ink-muted)]">
              Not connected — logging to local CSV
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
