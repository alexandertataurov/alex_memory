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

## Work authority

```text
WORK CONTROL
Notion

IMPLEMENTATION TRUTH
Repository code + tests

IMPLEMENTATION HISTORY / MIRRORS
TASKS.md + ExecPlans + CHANGELOG + docs
```

Notion is the sole source of truth for task existence, scope, status, priority,
sequence, dependencies, gates, owner actions, authorization, promotion,
completion, and the next executable leaf. Code and tests are authoritative
evidence of current behavior, but cannot independently change work control.
Repository task files and prose are synchronized mirrors/history.

## Working agreement

Start substantial work with the repository skill `alex-memory-loop`, which wraps
the narrower Notion skills. It must open **Codex — Ready & Authorized**, select
the lowest-sequence unblocked implementation leaf, build a live execution packet
from current Notion state plus relevant code/tests, and work only within that
authorized leaf. A Notion-authorized leaf does not require a `Repo ID`; that
field is only a cross-reference. Do not create, move, promote, reprioritize,
authorize, unblock, or close work from repository state.

Use an ExecPlan only within an authorized Notion task for migrations,
backfills, broad rebuilds, cross-cutting architecture, model/routing
migrations, or non-obvious deletion. An ExecPlan records implementation detail
and never authorizes a scope change; resolve scope changes in Notion first.

### Change classes

Classify each leaf before implementation:

- **Fast** — small, local, reversible change with no schema/data migration and no
  cross-cutting behavior. Run targeted tests, Ruff, completion evidence, and
  commit. Update only material mirrors.
- **Standard** — ordinary product or engineering change spanning multiple files
  or behavior boundaries. Run targeted tests during iteration and `make check`
  before completion. Update affected docs/changelog when materially required.
- **Risky** — migration, backfill, destructive work, security-sensitive change,
  broad architecture/routing change, or operation that can affect persistent
  data. Use an ExecPlan, backup/dry-run where applicable, targeted tests, and
  `make verify` before completion.

After each coherent implementation increment, run targeted tests. Before
closing a Standard task, run `make check`; before closing a Risky task, run
`make verify`. Patch-time hooks are intentionally lightweight and do not replace
completion gates.

Before finishing, inspect callers and failure paths as well as tests. After
verification, update the authoritative Notion task's outcome, status, gates,
and dependencies, then synchronize only material repository mirrors to that
final Notion state. If code/tests contradict a Notion assumption, report the
evidence and resolve the task in Notion before changing scope.

After completing a leaf, query **Codex — Ready & Authorized** again and continue
automatically with the next independently authorized leaf. Stop only for a real
gate: Owner Acceptance, Operator Authorization, destructive or migration
approval, scope ambiguity that changes product direction, or multiple equally
valid product choices.

Report task ID, changed behavior/files, change class, migration (or none),
tests, docs, limitations, and next Notion-authorized leaf. Do not add generic
managers, factories, wrappers, placeholder success paths, broad exception
swallowing, or speculative extension points.

## Commands

```bash
uv sync          # sync .venv from uv.lock
make check       # Standard completion gate
make verify      # Risky completion gate
make db-check    # read-only SQLite integrity check
make db-backup   # SQLite API backup before risky live schema work
make review      # code-size and hygiene signals
make codex-check # complete Codex workflow/handoff gate
```

Use `make help` for the full command list. This directory is a Git repository;
review `git status`, stage only intended files, and do not add or change remotes
or rewrite history without owner approval. `.env`, `data/`, sessions, logs,
media, and backups are private: never print, commit, or copy their contents.

## Codex harness

Repository skills are under `.agents/skills/`; project review roles and command
rules are under `.codex/`. Native Codex memory supplements, but never replaces,
checked-in architectural truth. Use focused review roles only for independent
work; their read-only limits are deliberate. Command rules are guardrails, not
a sandbox or authorization substitute.

## Notion work control and project memory

The configured `notion` MCP server is the sole source of truth for Alex Memory
development work control and product intent/history. The `alex-memory-loop`
skill is the default entrypoint; it may use `notion-context`, `notion-status`,
`notion-find`, `notion-task`, and `notion-sync` internally when their narrower
behaviors are needed.

Start work from **Codex — Ready & Authorized**, retrieve only the selected task
and targeted context, and generate a fresh execution packet rather than trusting
a stale stored Prompt as a complete implementation instruction. `TASKS.md`,
ExecPlans, changelog, docs, and GitHub prose are synchronized implementation
mirrors. If a mirror conflicts with Notion, Notion wins; if code or tests
contradict a Notion assumption, report it and resolve the task in Notion before
changing scope.
