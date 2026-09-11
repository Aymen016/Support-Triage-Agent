# Support Triage Agent

> A small business gets 40-80 support emails a day. One person manually reads each one,
> decides if it's urgent, figures out which category it belongs to, writes a reply, and
> copies the details into a spreadsheet. It takes 3 hours a day and things fall through
> the cracks.
>
> This agent does the first 90% automatically and hands a human a queue of pre-drafted,
> pre-classified replies to approve in one click. **Nothing sends without a human approving it.**
<img width="3405" height="1215" alt="Main-dashboard" src="https://github.com/user-attachments/assets/134724f2-740e-4ecb-8b38-ae770b8152fc" />


--- 


## Status

| Phase | What | Status |
|---|---|---|
| 1 | 50 labelled fixture emails | ✅ Done |
| 2 | Tools as plain, independently-testable functions | ✅ Done |
| 3 | Agent loop (LLM chooses which tool to call) | ✅ Done |
| 4 | Human-in-the-loop review gate + DB persistence | ✅ Done |
| 5 | FastAPI backend | ✅ Done |
| 5 | React dashboard (Review Queue / Runs / Settings) | ✅ Done — redesigned as a full app shell (sidebar, top bar, light/dark mode) and verified end-to-end in a real browser (screenshots, zero console errors), not yet used against a real Anthropic key |
| 6 | Real Gmail + Google Sheets integrations | ✅ Done — needs a real Google Cloud OAuth app + one-time `python -m integrations.google_auth` bootstrap to actually exercise live (see Setup) |
| 7 | Evaluation | 🟡 Classification + urgency accuracy work today; escalation precision/recall and draft-quality scoring still need the full-loop eval extension |

68 backend tests pass (`pytest tests/ -v`), all against a free offline `FakeLLMClient` / `ScriptedOrchestrator` pair (and mocked Gmail/Sheets APIs) — nothing costs money, needs a key, or hits a real Google API to verify the logic. The frontend builds clean (`npm run build`), lints clean (`npm run lint`), and has been driven end-to-end with a headless browser (Review Queue, email detail, approve-confirmation modal, dark mode) with zero console errors.

### What's actually working right now

**Data & tools (Phases 1-2)**
- 50 hand-written fixture emails (`ingest/fixtures/`), labelled with expected category/urgency/escalation, covering every bucket the plan calls for — including deliberately awkward ones (vague, non-English, multi-issue, thread-replies).
- All 6 tools as plain, typed functions, each validating its own output and returning a structured `ToolError` instead of raising.

**Agent loop (Phase 3)**
- A real Anthropic tool-calling orchestrator (`agent/orchestrator.py`) plus an offline `ScriptedOrchestrator` for free testing.
- Handles every failure mode the plan calls out: hallucinated tool names, malformed arguments (one retry, then forced escalation), an 8-step hard cap, and forced escalation when `classify_email`'s confidence is below threshold — the model's own judgment about its low-confidence call isn't trusted.
- **Caught a real bug while building this**: the test double for the orchestrator was stateful and got silently reused across a batch of 50 emails, so 49 of them wrongly escalated. Fixed by making orchestrators fresh-per-email. Worth mentioning in an interview — it's exactly the kind of thing the "Runs" audit screen exists to catch.

**Human-in-the-loop gate + persistence (Phase 4)**
- SQLAlchemy models for emails, classifications, drafts, escalations, and every agent step.
- `approve_email()` is the *only* path to "sent" — verified you can't double-approve, can't approve an already-escalated email, edits are stored separately from the original draft, and rejections are tracked for the improvement dataset (Stretch Goals).

**Backend API (Phase 5)**
- Full FastAPI app: review queue, email detail, approve/reject/escalate, a blocking `/run` and a live SSE `/run/stream` for step-by-step progress.
- A real **Settings** endpoint — confidence threshold and tone instructions actually change agent behavior on the next run, not just cosmetic. Category routing notes get fed straight into the classifier's prompt, so a non-engineer can tune edge cases without a code change.

**Frontend (Phase 5, redesigned as a full app shell)**
- Vite + React 19 + TypeScript + Tailwind v4. Persistent collapsible **sidebar** (Review Queue / Runs / Settings, plus a live SYSTEM section showing Gmail / Google Sheets / AI Agent connection status) and a **top bar** (page title, light/dark toggle, notifications, Gmail connection pill, user avatar).
- **Review Queue** (the renamed, redesigned Inbox): keyboard-driven (J/K navigate, `⌘K` search, A/E/R to act), status + category filters, a proper email-reader layout, a polished **AI Analysis** card (category/urgency/confidence, plus customer name/order-id parsed from the existing audit-step data — all real, nothing fabricated), and an **AI Draft** card (Copy/Edit/honestly-disabled-Regenerate) with an **Approve & Send confirmation modal** showing the exact recipient and final text before anything is marked sent.
- **Light/dark mode** — a deliberately-designed dark palette (not a naive inversion), defaults to system preference, persists your explicit choice, applied with zero flash-of-wrong-theme on load.
- Toast notifications, skeleton loading states (replacing plain "Loading…" text), and a new read-only `GET /integrations/status` endpoint powering the shell's connection indicators.
- Runs and Settings pages unchanged visually in this pass (still on the original design) but automatically pick up the new dark-mode palette since every page already shared the same CSS custom-property tokens.
- Verified end-to-end with a headless-browser pass (Review Queue, email detail, approve modal, category filter, dark mode) — zero console errors.

**Gmail + Google Sheets integration (Phase 6)**
- Real Gmail ingestion via OAuth (`ingest/gmail_client.py`): polls `GMAIL_LABEL_TO_POLL`, parses messages (including multipart/HTML fallback) into the same flat shape fixtures use, and swaps the label off each processed message. `send_reply()` sends the approved draft as a real, correctly-threaded reply once `approve_email()` calls it.
- Real Google Sheets logging (`agent/tools/sheets.py`): `log_to_sheet()` auto-detects — real Sheets if `GOOGLE_SHEETS_SPREADSHEET_ID` + Gmail OAuth are configured, local CSV otherwise, same auto-detect spirit as `build_llm()`.
- One shared OAuth module (`integrations/google_auth.py`) — a single consent grant (`gmail.modify` + `spreadsheets` scopes) covers both, via a one-time CLI bootstrap (`python -m integrations.google_auth`), never triggered from a live request.
- `IncomingEmail.source` ("fixture" | "gmail") gates whether `approve_email()` may attempt a real send — fixture-sourced emails (the free/offline demo path) never trigger one, even if Gmail happens to be configured.
- A real send failure during approval blocks the approval itself (`SendError`, a `GateError`) — the draft stays `"pending"` rather than being falsely marked approved. Sheets-logging failures, by contrast, don't block approval (same best-effort behavior as before — it's an audit trail, not the send guarantee).
- Fully testable offline: all Gmail/Sheets API calls are mocked in tests (`tests/test_google_auth.py`, `tests/test_gmail_client.py`, plus the Sheets branch in `tests/test_tools.py`) — no real Google credentials needed to run the suite.

### What's next

1. **Exercise Phase 6 live** — the Gmail + Sheets code is written and unit-tested against mocked APIs, but has not been run against a real Google Cloud project/inbox yet (this sandbox can't reach Google's APIs). See "Setup — Phase 6" below for the one-time OAuth bootstrap, then a live smoke test: label a real test email, `POST /run`, approve it, and confirm the reply sends and a row lands in the Sheet.
2. **Extend the redesign to Dashboard/Overview, Analytics, Knowledge Base, Activity Log, and a full Integrations page** — the Review Queue and app shell are done; those screens don't exist yet.
3. **Phase 7 extension** — `eval/run_eval.py` currently scores classification + urgency; escalation precision/recall and draft-quality scoring need the full loop wired in.

---

## Setup

### Backend
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY for real classification; omit it to run on the free offline fake
uvicorn api.main:app --reload
```
Docs at http://localhost:8000/docs. Without `ANTHROPIC_API_KEY` set, `/run` and `/run/stream` automatically fall back to the offline `FakeLLMClient` + `ScriptedOrchestrator` pair and say so in the response (`used_fake_llm: true`) — never silently pretends fake results are real accuracy.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Opens on http://localhost:5173, expects the backend on :8000 (override with `VITE_API_BASE`).

### Setup — Phase 6 (real Gmail + Sheets)
Optional — without this, `/run` keeps using fixtures and local-CSV logging exactly as before.
1. In Google Cloud Console: create a project (or reuse one), enable the **Gmail API** and **Google Sheets API**, then create an OAuth **Desktop app** Client ID. Put its client ID/secret in `.env` as `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET`.
2. In Gmail, create a label to poll (default `support` — matches `GMAIL_LABEL_TO_POLL`) and apply it to the emails you want the agent to see.
3. Create a Google Sheet, add a header row (`row_id, timestamp, email_id, sender, category, urgency, action_taken, approver`), and put its spreadsheet ID (from its URL) in `.env` as `GOOGLE_SHEETS_SPREADSHEET_ID`.
4. Run the one-time interactive OAuth bootstrap (opens a browser, needs a human to approve the consent screen — never run this from a server):
   ```bash
   python -m integrations.google_auth
   ```
   This mints `data/google_token.json` (gitignored), covering both Gmail and Sheets with one consent grant. `POST /run` and `approve_email()` pick up real Gmail/Sheets automatically from then on — no restart-time config needed beyond this file existing.

## Run the tests
```bash
pytest tests/ -v          # backend — 68 tests, no API key or Google credentials needed
cd frontend && npm run build && npm run lint   # frontend — type-checks and lints
```

## Regenerate fixtures
```bash
python -m ingest.generate_fixtures
```

## Run the eval
```bash
python -m eval.run_eval --fake     # free, sanity-check only
python -m eval.run_eval            # real Claude, needs ANTHROPIC_API_KEY in .env
```

---

## Design decisions

- **Fixtures before Gmail.** OAuth teaches you nothing about whether the agent classifies well. The 50 fixtures double as the eval set.
- **Every tool returns a structured error, never raises.** The agent loop needs to look at a result and decide what to do next — retry, escalate, continue — without a try/except around every call.
- **Most tool arguments come from loop state, not the model.** `classify_email` and `extract_customer_info` take no model-supplied arguments at all — the loop already knows the email being processed. Asking the model to retype subject/body into a tool call wastes tokens and risks transcription errors.
- **`log_to_sheet` isn't a model-choosable tool.** Per the architecture diagram, sheet logging happens after human approval, not mid-loop — the loop calls it directly and deterministically at a terminal state.
- **A successful draft or escalation ends the run immediately.** No asking the model if it wants to keep going once the goal state is reached — keeps behavior predictable and auditable.
- **Nothing sends automatically.** `approve_email()` is the only path to "sent," full stop — see Phase 4 tests for what that guarantees.
- **A real send failure blocks approval, a real Sheets-logging failure doesn't.** If `approve_email()`'s Gmail send fails, the draft stays `"pending"` rather than being marked approved without actually being sent — that would violate the one send-path invariant above. Sheets logging is an audit trail, not the send guarantee, so it stays best-effort (matching its pre-Phase-6 behavior).
- **Gmail + Sheets reuse one OAuth grant, not a service account.** `integrations/google_auth.py` is the single shared auth module both `ingest/gmail_client.py` and `agent/tools/sheets.py` depend on — one consent screen, one cached token, two scopes (`gmail.modify`, `spreadsheets`).
- **The frontend only ever shows real data.** No fabricated sentiment score, no invented category taxonomy, no made-up accuracy metrics — every number/badge in the Review Queue traces back to an actual backend field. Where a described feature (e.g. "Regenerate draft") isn't wired up yet, it's shown visibly disabled with an honest tooltip rather than faked.

## Known limitations (honest, as of this point in the build)

- Only the app shell + Review Queue have been redesigned — Runs and Settings still use the original (pre-redesign) layout; Dashboard, Analytics, Knowledge Base, and Activity Log pages the plan calls for don't exist yet.
- `search_knowledge_base` is keyword overlap, not real embeddings — fine for 8 sample articles, won't scale to a real KB.
- Confidence threshold is global, not per-category (Settings UI says so).
- Auto-send toggle (`auto_send_enabled` in Settings) is stored but still inert — approval always requires a human click; nothing auto-sends on its own even with Gmail configured.
- Gmail polling fetches one page (25 messages) per `/run` call, no auto-pagination — a large backlog needs a few manual re-runs to fully drain.
- Gmail/Sheets code is implemented and unit-tested against mocked APIs, but hasn't been run against a real Google Cloud project/inbox yet (see "What's next").
- Eval only covers classification + urgency accuracy so far, not escalation precision/recall or draft quality.
