# AM-092 — Engineering Harness

## Objective

Create the smallest durable Codex/Python harness that improves Alex Memory
development quality, and restore the current quality baseline without touching
private Telegram data.

## Current and target state

The baseline has pytest, Ruff, mypy, pre-commit, VS Code support, and safe
developer diagnostics but no lockfile, CI, repository-local Codex roles/skills,
or dependency/security gate. The initial gate has three failing tests, one
unused import, and stale generated development documentation.

The target uses a PEP 621 project definition plus `uv.lock`, preserves the
existing fast gate, adds explicit full verification, documents the workflow,
and provides focused local Codex skills, restricted review roles, and command
rules. It does not alter global Codex model/memory defaults or external
permissions. A pending, derived-only FTS migration may be applied only after a
SQLite API backup and integrity review.

## Constraints

- Raw evidence, session files, credentials, manual corrections, and live
  SQLite data remain untouched.
- No new MCP, plugin, or browser stack without a demonstrated project need.
- No broad lint family is enabled until its current findings are deliberately
  resolved.
- Dependency migration must be reproducible and remove old declarations only
  after the locked environment validates.

## Affected areas

`pyproject.toml`, dependency files, `Makefile`, `scripts/dev_tools.py`, root
guidance, `docs/`, `.agents/skills/`, `.codex/`, baseline tests, and the Daily
Brief query.

## Implementation sequence

1. Record the baseline and research supported Codex, uv, Ruff, dependency, and
   audit workflows.
2. Repair the baseline lint/test regressions, including source-date Daily Brief
   semantics.
3. Add the locked Python workflow and run dependency/security checks.
4. Add compact guidance, plans, skills, review roles, and command rules.
5. Regenerate docs, review changes independently, run the full gate, and move
   this plan to completed.

## Risks and decisions

- `uv sync` is exact by default, so it is run only after declarations are
  reviewed and against the existing local virtual environment.
- Context7, GitHub MCP, Serena, and Playwright are not added unless a supported
  integration materially improves this local terminal application.
- Codex rules are guardrails, not a sandbox; the new rules document that limit.

## Validation plan

Run focused regression tests, `make verify`, `make db-check`, `uv lock --check`,
`deptry`, `pip-audit`, Codex rule checks, and the skill validator. Review
callers and the final changed files independently.

## Progress and discoveries

- 2026-08-24: Audit complete. Codex CLI 0.146.1 supports stable memories,
  hooks, skills, rules, plugins, and multi-agent roles. Global Codex defaults
  are already `gpt-5.6-terra` with `xhigh` reasoning and native memory enabled.
- 2026-08-24: Baseline is 123/126 tests passing, 67% coverage; format and
  mypy pass; one unused import, stale development docs, and no dependency lock
  exist. SQLite integrity is clean at schema version 11.
- 2026-08-24: Applied the existing migration 12 after a SQLite API backup to
  rebuild only FTS indexes. The post-migration check reports integrity and
  source/index parity across all six FTS contracts; raw and canonical records
  were not changed.
- 2026-08-24: Independent review found the original migration-12 rebuild was
  not atomic because `executescript()` committed before its rebuild script.
  The rebuild now starts and retains an explicit transaction through parity and
  ledger recording; a forced trigger-creation failure proves rollback. Review
  also found the session-lock ignore gap and stale Git guidance, both repaired.

## Final outcome

Completed on 2026-08-24. The project now has a locked Python environment,
focused dependency/security and complete verification gates, compact Codex
guidance, skills, roles, rules, and execution plans. The full gate passes with
134 tests; Ruff, formatting, MyPy, generated docs, the lockfile, deptry,
pip-audit, SQLite integrity, and all FTS contracts are clean. No migration was
created; the pre-existing migration 12 was applied after a SQLite API backup.

The local Git repository is intentionally still uncommitted. Pre-commit is
installed, but `pre-commit run --all-files` selects no untracked paths until
the owner stages the intended initial files; no files were staged or committed
by this work.
