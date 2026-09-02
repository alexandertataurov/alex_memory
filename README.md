# Alex Memory

Telegram archive with a resumable, multi-provider AI memory layer.

## Developer quick start

Alex Memory is a local, source-backed operational memory system. Telegram is
the current evidence source; AI findings are validated before they affect
canonical people, tasks, projects, summaries, or temporal context.

```text
Raw Telegram evidence → validated AI observations → events / temporal facts
→ canonical state → bounded context → search, briefs, tasks, and Q&A
```

```bash
# Install uv first: https://docs.astral.sh/uv/getting-started/installation/
uv sync
cp .env.example .env
# Add only your real Telegram credentials to .env.
code .
```

VS Code will recommend Python, Pylance, Ruff, and debug support. It uses the
repository `.venv`, discovers pytest tests, and includes interactive, daemon,
and current-test debug profiles. The daemon profile starts a live Telegram
sync; use it deliberately.

Common development commands:

```bash
make run          # interactive UI plus live sync
make daemon       # unattended local daemon
make test
make lint
make format
make format-check
make typecheck
make check
make lock-check
make deps
make audit
make verify
make health
make db-check
make db-backup
make docs
make docs-check
make changes
make tasks
make review
make codex-check
```

Run `make help` for the complete command summary. This directory has existing
Git history and a configured remote. Review `git status` and stage only
intended files; do not change the remote or rewrite history without owner
approval.

`data/telegram.sqlite` is a live WAL database and `alex_memory.session` is
private session material. Never commit, print, reset, or copy them casually.
Use `make db-backup`, which uses SQLite's backup API, before risky schema work.

Development work is tracked in `TASKS.md`. Read `AGENTS.md` before substantial
changes, then update tests, docs, `CHANGELOG.md`, and `docs/CHANGES.md` from a
reviewed diff. Detailed system documentation lives in `docs/`.

## Operational memory

Successful AI batches are retained as source-backed findings, then safely
projected into a second operational layer:

- Canonical people, companies, projects and aliases use exact Telegram IDs,
  usernames, then normalized aliases. Ambiguous aliases create review records;
  they are never merged automatically.
- Tasks reconcile promises, deadlines and waiting states only at or above
  `AI_AUTO_ACCEPT_CONFIDENCE`; reviewable uncertainty is placed in
  `review_queue`. A manual task status locks that status against later AI edits.
- Each completed batch creates a memory chunk and refreshes per-chat daily and
  monthly summaries. Daily Briefs are structured, stored in SQLite, and can be
  regenerated without re-running Telegram analysis.
- SQLite FTS5 tables and triggers index new messages, tasks, memory and chunk
  summaries when supported by the local SQLite build. Search also has a safe,
  bounded all-term SQL fallback with the same word-order-independent candidate
  semantics for legacy records and FTS-less installations.

## Continuous Telegram sync

Starting the app runs one policy-driven Telegram synchronization lifecycle:
it inventories dialogs, bootstraps personal/small-group history fully, bounds a
large group's initial import to recent history, catches up, installs live
handlers, and reconciles incrementally every 30 minutes.
Incoming writes are serialized through the SQLite queue; edited and deleted
messages preserve audit history instead of creating duplicate records.

```bash
python src/main.py            # interactive UI with live sync in the background
python src/main.py --daemon   # unattended local sync daemon
```

Optional scheduling controls:

```env
TG_RECONCILE_ENABLED=true
TG_RECONCILE_INTERVAL_MINUTES=30
TG_ITER_MESSAGES_WAIT_SECONDS=0.2  # fast, bounded MTProto request rate
AI_AUTO_ANALYZE_NEW_MESSAGES=true
AI_AUTO_ANALYZE_INTERVAL_MINUTES=15  # durable-work maximum recheck interval
HISTORY_AUTO_ANALYZE=false
HISTORY_AUTO_ANALYZE_INTERVAL_MINUTES=60  # minimum interval between history attempts
DAILY_BRIEF_AUTO_GENERATE=false
DAILY_BRIEF_TIME=08:00
APP_TIMEZONE=Asia/Tbilisi
```

## Terminal interface

`make run` opens the Textual relationship-intelligence interface. Its home
screen focuses People search immediately; results filter locally by canonical
name, alias, username, and linked projects with deterministic fuzzy ranking.
Enter opens a bounded person overview, and Ctrl+K opens the command palette.
Ask Memory stays separate, so ordinary search does not invoke AI.

The existing interactive and daemon entry points retain their behavior. The
terminal redesign changes no schema.

## Operational intelligence

The terminal now includes **Ask Alex Memory**, attention items, follow-ups,
projects, people/company profiles, unified search, and a review queue.

The home screen groups commands into **Focus**, **Explore**, and **Maintain**.
**Today** and **Follow-ups** are visible Focus actions; **Refresh operational
state** is the explicit Maintain action that evaluates deterministic follow-ups
and project health. Use the highlighted letters (`n` for Today, `a` to ask,
`t` for tasks, `s` to search, and `y` to sync), type a command name, or keep
using the original menu numbers.
Pressing Enter opens Ask Alex Memory; blank questions and searches return to
the home screen without running work. Profile and context screens list valid
canonical entities before asking for an ID, and entity/chat lists accept a text
filter and disclose when results are bounded.

- Retrieval is SQL-first and bounded: canonical tasks/entities lead, then
  summaries, durable memory, and finally raw Telegram evidence.
- Ask uses only retrieved records and validates numbered citations. Gemini is
  used first with Groq fallback; an unavailable provider returns the grounded
  local answer instead of inventing a response.
- Today, profiles, Search, and Ask are read-only. Waiting tasks create
  deduplicated follow-ups and project health/notification state is evaluated by
  the explicit refresh action or normal canonical-projection work.
- Cancelling a task manually records feedback and prevents a future identical
  low-confidence extraction from recreating it. `chat_ai_policy` can persist
  an explicit policy per chat: normal automatic routing, full semantic analysis,
  classification-only archiving, external-news-only analysis, or ignore.

```env
QA_MAX_RAW_MESSAGES=40
QA_MAX_TASKS=20
QA_MAX_MEMORIES=20
QA_MAX_SUMMARIES=15
QA_MAX_CONTEXT_CHARS=45000
QA_USE_LLM=true
FOLLOW_UP_WAITING_AFTER_DAYS=3
PROJECT_STALE_DAYS=10
PROJECT_CRITICAL_STALE_DAYS=21
NOTIFICATION_REPEAT_HOURS=24
```

## Context and memory intelligence

The `alex_memory.context` subsystem keeps a source-backed model above raw
messages: immutable observations become canonical events, temporal facts, and
SQL relationships. A changed current fact closes the prior validity interval;
it never overwrites history. Context builders accept an `as_of` timestamp and
prioritize pinned/canonical state, tasks, events, summaries, then bounded raw
evidence.

New safe SQLite tables include `context_events`, `context_facts`,
`relationships`, `context_conflicts`, `context_summary_versions`,
`global_state_snapshots`, `pinned_memory`, and `temporal_resolutions`.

```env
CONTEXT_MAX_CHARS=50000
CONTEXT_MAX_RAW_MESSAGES=30
CONTEXT_MAX_EVENTS=30
CONTEXT_MAX_FACTS=50
CONTEXT_MAX_TASKS=30
CONTEXT_MAX_SUMMARIES=15
```

## AI architecture

- Gemini (`gemini-3.5-flash-lite`) is the default primary provider.
- Groq remains available as the fallback provider.
- Daily work processes messages newer than the latest completed Daily cursor.
- **Analyze All History** continues through every eligible message and resumes
  after interruption. Provider-safe windows remain an internal detail.
- Messages are marked analyzed only after the response and extracted items are saved in one transaction.

## What is fixed

1. **AI analyzed count is now truthful**
   - Empty/media-only Telegram messages are no longer inserted into `ai_message_state`.
   - Existing legacy `batch_id=NULL` markers for empty messages are cleaned automatically on startup.
   - Status now shows `AI text messages total / AI actually analyzed / AI text backlog`.

2. **Groq results are now visible**
   - After every analysis run the terminal shows per-batch summary, returned items, saved items, duplicates and rejected items.
   - Returned findings are printed immediately.
   - If Groq returns zero items, you still see its summary of each batch.

3. **Silent item loss is fixed**
   - Source references are validated against the exact submitted batch before results are accepted.
   - Bad references cause the batch to fail instead of silently dropping findings and marking messages analyzed.
   - Full Groq JSON response and counts are stored in `ai_batches` for diagnostics.

4. **Stronger extraction prompt**
   - Explicitly recognizes requests, commitments, waiting-for, follow-ups, deadlines, payments and projects.
   - A non-empty summary is required by application validation for every successful batch.

5. **AI diagnostics screen**
   - Menu option shows recent batches, summaries/errors, returned/saved/rejected counts.

## Upgrade

Back up your source directory, then copy the new `src` directory into your existing project.
Keep your existing:

- `.env`
- `data/telegram.sqlite`
- `alex_memory.session`

The database is migrated automatically.

Add to `.env` if desired:

```env
AI_REPORT_BATCHES=20
```

Run:

```bash
source .venv/bin/activate
python src/main.py
```

## Development checks

The regression tests use Python's built-in test runner and do not call
Telegram or Groq:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The application now reports invalid numeric `.env` settings clearly instead
of silently clamping them. AI message text is treated as untrusted input,
one-time verification codes are redacted before analysis, and malformed
individual model findings are rejected while the rest of a batch is saved
normally.

The normal terminal surface is deliberately small: Today, Live Sync, Analyze
All History, Tasks, Follow-ups, People, Projects, Search, Ask Alex Memory,
Daily Brief, Context Graph, Review, Chat Policy, Refresh operational state,
and focused diagnostics. Diagnostics opens one selected view by default
(status, monitor, errors, analytics, settings, or all). Existing numeric
shortcuts remain available for compatibility. If Telegram cannot start after
the local database opens, the terminal remains available in local-read mode;
sync and analysis clearly report that they are unavailable.

## Reliability update

This build changes AI analysis behavior:

- AI analyzes personal chats only by default (`AI_INCLUDE_GROUPS=false`). Telegram still archives groups normally.
- Bot chats are always archived but never sent to AI. The first analysis run
  refreshes the dialog inventory so existing bot chats are excluded too.
- Set `AI_INCLUDE_GROUPS=true` if you explicitly want group messages sent to Groq.
- Personal chats are prioritized before groups when groups are enabled.
- Groq `APIConnectionError` / network failures are retried with backoff.
- If strict JSON Schema generation fails with Groq `failed_generation` / HTTP 400, the same batch automatically falls back to JSON Object mode and is validated locally.
- A bad individual `source_message_id` no longer destroys an otherwise successful batch; that item is rejected and reported individually.
- Failed batches now appear in the current-run report, not just in historical diagnostics.
- Recommended smaller AI batches: 30 messages / 9000 chars.

Recommended `.env`:

```env
# Routing
AI_PRIMARY_PROVIDER=gemini
AI_FALLBACK_PROVIDER=groq

# Gemini primary
GEMINI_API_KEY=
GEMINI_PRIMARY_MODEL=gemini-3.5-flash-lite
GEMINI_REQUESTS_PER_MINUTE=14.5
AI_AUTO_ACCEPT_CONFIDENCE=0.90
AI_REVIEW_CONFIDENCE=0.65

# Groq fallback
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b

# AI policy and lanes
AI_INCLUDE_GROUPS=false
AI_DAILY_MAX_MESSAGES=3000
HISTORY_INTERNAL_CONCURRENCY=20
HISTORY_INTERNAL_BATCH_MESSAGES=60
HISTORY_INTERNAL_BATCH_CHARS=12000
AI_CONTEXT_MESSAGES=10
AI_MAX_OUTPUT_TOKENS=1200
AI_REQUEST_TIMEOUT_SECONDS=90
AI_MAX_RETRIES=4
AI_RETRY_BASE_SECONDS=3
AI_REPORT_BATCHES=20
```

Install dependencies after updating the project:

```bash
uv sync
```
