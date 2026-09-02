# Quality

Alex Memory uses a small quality system that protects source-backed state
without treating every local edit as a release process.

## Canonical commands

```bash
uv sync
make hooks        # install local Git hooks after `uv sync`
make check        # compile, tests, lint, formatting, types
make verify       # check + docs + lock + dependencies + vulnerability audit + DB
make db-check
make review
make codex-hooks-check
```

`make check` is the fast deterministic gate for normal changes. `make verify`
is the full local gate before handing off a substantial change. `make audit`
uses a vulnerability service and therefore needs network access; it is kept
separate from the fast edit loop.

## Git hooks

After cloning, run `uv sync` and `make hooks`. The pre-commit hook rejects
trailing whitespace, missing final newlines, invalid YAML, added files over
1 MiB, Ruff lint/format violations, and an out-of-date `uv.lock`. It runs
Ruff 0.16.4, matching the locked project toolchain. `make check` remains the
authoritative fast gate because tests and type checking are intentionally not
run on every commit.

## Codex workspace guardrails

`.codex/hooks.json` provides lightweight workflow guardrails alongside the
existing repository rules and quality commands. On the first session where
Codex discovers local hooks, review and trust them through `/hooks`. They are
not a sandbox, a substitute for permissions, or a correctness/security
boundary.

- Session start prints only branch, changed-path count, the first active task,
  and canonical `.venv`/`uv` guidance.
- Pre-tool checks reject obvious access to private archives, secrets, Telegram
  sessions, logs/media/backups, and broad destructive Git/filesystem commands.
- Post-patch checks run Ruff and MyPy only for changed maintained Python files.
- Stop asks for proportionate verification when a change is claimed and reports
  a small legacy/placeholder diff review against the repository baseline.

Run `make codex-hooks-check` after editing hook scripts or their JSON. The six
project skills under `.agents/skills/` are invoked by scope, not by loading all
instructions into every task. Keep plugins and skills on-demand; remove a tool
when it duplicates this workflow or its measured evaluation does not justify
its instruction cost.

## Change discipline

Start from an existing task in `TASKS.md` or create one. Use an ExecPlan for a
schema migration, backfill, broad derived-state rebuild, cross-cutting
architecture change, model/routing migration, or cleanup whose deletion risk
is not locally obvious. Plans live in `docs/exec-plans/` and record the
objective, state transition, constraints, affected modules, validation,
discoveries, and final outcome.

For a bug, reproduce it, trace the full call path, state a falsifiable root
cause, implement the smallest correct change, and add a behavioral regression.
For refactoring, establish a baseline and find callers before moving code. For
performance work, measure the actual query or workload before and after. Do
not create generic managers, factories, or wrappers without an existing shared
responsibility.

## Tests and hygiene

Tests must use isolated databases and may not authenticate with Telegram or
write the production database. Test behavior, error paths, idempotency, and
authority boundaries rather than private implementation details. New code
should not introduce broad exception swallowing, placeholder behavior, copied
derived state, undocumented compatibility layers, or unbounded AI/database
work.

## Diagnostic metric domains

- History coverage counts eligible non-deleted text messages. `classified`
  requires the current classification version and a non-stale classification;
  `semantic`, `canonicalized`, and `context_integrated` additionally require
  the current analysis version and a non-stale analysis record. `current_enough`
  additionally requires clean, satisfied context dependencies.
- Graph route counts partition classification rows in priority order: archive,
  news, operational, state change, then contextual. They are counts, not a
  percentage or graph-completeness claim.
- Provider diagnostics preserve a missing provider as `router`; it is not
  attributed to a fallback provider. Live routing state comes from the router;
  terminal routing output combines current registry eligibility with durable
  route-event and quota records.

Ruff enforces correctness plus bugbear and the one Python-3.12 modernization
rule that fits this codebase today. Broader rule families remain opt-in until
their findings are reduced deliberately; a large ignored lint backlog is not a
quality gate. Deptry checks declared dependencies, while `pip-audit` checks the
synced environment for known advisories. Neither replaces code review.

## Review and cleanup

Before finishing a substantial change, inspect affected callers, persistence
and failure paths, run the proportional commands above, update docs and the
changelog, and obtain an independent review. Keep only real technical debt in
`docs/TECH_DEBT.md`; record a concrete consequence and next action rather than
a vague cleanup wish.
