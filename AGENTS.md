# Alex Memory — Engineering Guide

Alex Memory is a local, source-backed temporal context engine for personal
operations. Telegram is the current ingestor; Gmail, WhatsApp, iMessage, and
Drive must enter the same evidence-first model.

## Orientation

```text
Evidence → observations → events / temporal facts → canonical state
→ bounded context → intelligence and actions
```

- `telegram/`: archive, live sync, and bounded SQLite writer.
- `ai/`: bounded batches, Gemini/Groq routing, and local result validation.
- `operational.py`: canonical entities, tasks, briefs, and projection.
- `context/`: temporal state, relationships, and materialized context.
- `intelligence.py`: retrieval, grounded Q&A, attention, and profiles.

Start with [architecture](docs/ARCHITECTURE.md), [data model](docs/DATA_MODEL.md),
[AI pipeline](docs/AI_PIPELINE.md), [quality](docs/QUALITY.md),
[security](docs/SECURITY.md), and [execution plans](docs/PLANS.md).

## Non-negotiable invariants

- Raw evidence stays traceable; never replace it with model interpretation.
- Close temporal validity intervals; never rewrite historical state.
- Manual corrections outrank AI inference; ambiguous identity goes to Review.
- Validate untrusted AI output locally with source references. Provider failure
  must not stop Telegram ingestion or claim incomplete work as successful.
- Keep queues, queries, and AI context bounded. Deterministic IDs, dates,
  joins, quotas, and scoring belong in Python or SQL.
- Tests use temporary databases only. Never authenticate with Telegram or write
  the production database.

## Working agreement

Before substantial work, open Notion's **Codex — Ready & Authorized** view and
select its lowest-sequence unblocked implementation leaf. Read that task's
Prompt, structured fields, dependencies, gate fields, Owner Action, and parent
task. Then inspect the relevant repository architecture, tests, config, schema,
and any `TASKS.md`/ExecPlan mirror. A Notion-authorized leaf does not require a
`Repo ID`; that field is only a cross-reference. Do not create, move, promote,
reprioritize, authorize, unblock, or close work from repository state.

Use an ExecPlan only within an authorized Notion task for migrations,
backfills, broad rebuilds, cross-cutting architecture, model/routing
migrations, or non-obvious deletion. An ExecPlan records implementation detail
and never authorizes a scope change; resolve scope changes in Notion first.
Work only within the selected leaf: task → smallest coherent change → tests →
repository mirrors → Notion outcome/gate/status → commit.

Before finishing, inspect callers and failure paths as well as tests. After
verification, update the authoritative Notion task's outcome, status, gates,
and dependencies, then synchronize `CHANGELOG.md`, `docs/CHANGES.md`, affected
docs, `TASKS.md`, and any ExecPlan to that final Notion state. If code/tests
contradict a Notion assumption, report the evidence and obtain a deliberate
Notion update, narrowing, or closure before changing scope. Report task ID,
changed behavior/files, migration (or none), tests, docs, limitations, and next
Notion-authorized leaf. Do not add generic managers, factories, wrappers,
placeholder success paths, broad exception swallowing, or speculative extension
points.

## Commands

```bash
uv sync          # sync .venv from uv.lock
make check       # fast deterministic gate
make verify      # complete local gate
make db-check    # read-only SQLite integrity check
make db-backup   # SQLite API backup before risky live schema work
make review      # code-size and hygiene signals
make codex-check # complete Codex handoff gate
```

Use `make help` for the full command list. This directory has a local Git
repository but no initial commit yet; review `git status`, stage only intended
files, and do not add a remote or rewrite history without owner approval.
`.env`, `data/`, sessions, logs, media, and backups are private: never print,
commit, or copy their contents.

## Codex harness

Repository skills are under `.agents/skills/`; project review roles and command
rules are under `.codex/`. Native Codex memory supplements, but never replaces,
checked-in architectural truth. Use focused review roles only for independent
work; their read-only limits are deliberate. Command rules are guardrails, not
a sandbox or authorization substitute.

## Notion work control and project memory

The configured `notion` MCP server is the sole source of truth for Alex Memory
development work control: task existence, scope, status, priority, sequence,
dependencies, gates, owner actions, authorization, promotion, completion, and
the next executable leaf. It also holds product intent and history. Use the
repository skills `notion-context`, `notion-status`, `notion-find`,
`notion-task`, and `notion-sync` when their descriptions apply.

Start work from **Codex — Ready & Authorized**, then retrieve only the selected
task and any needed targeted context. `TASKS.md`, ExecPlans, changelog, docs,
and GitHub prose are synchronized implementation mirrors. Repository code and
tests are authoritative evidence of current behavior, but cannot independently
alter work control. If a mirror conflicts with Notion, Notion wins; if code or
tests contradict a Notion assumption, report it and resolve the task in Notion
before changing scope.
