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

Before substantial work, read `TASKS.md`, inspect the relevant architecture,
tests, config, and schema, then create or move one task to **Now**. Use an
ExecPlan for migrations, backfills, broad rebuilds, cross-cutting architecture,
model/routing migrations, or non-obvious deletion. Work in the order: task →
smallest coherent change → tests → docs → changelog → verification.

Before finishing, inspect callers and failure paths as well as tests. Update
`CHANGELOG.md`, `docs/CHANGES.md`, affected docs, `TASKS.md`, and the ExecPlan.
Report task ID, changed behavior/files, migration (or none), tests, docs,
limitations, and next task. Do not add generic managers, factories, wrappers,
placeholder success paths, broad exception swallowing, or speculative
extension points.

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

## Notion project memory

The configured `notion` MCP server is a bounded source of Alex Memory product
intent and history: goals, roadmap, AI/context architecture decisions, profile
requirements, task definitions, UI decisions, known debt, blockers, rejected
ideas, and prioritization. Use the repository skills `notion-context`,
`notion-status`, `notion-find`, `notion-task`, and `notion-sync` when their
descriptions apply.

Do not query Notion for a self-contained fix or a small implementation change.
For historical or business context, retrieve lazily: identify the concrete
Alex Memory entity/topic, search it, fetch only the smallest relevant set, and
compare the findings against current code and `TASKS.md`. The repository is
authoritative for current implementation; Notion records intent and decisions.
If either is stale, superseded, completed, rejected, or conflicts with the
other, say so and do not turn it into unrequested feature work.
