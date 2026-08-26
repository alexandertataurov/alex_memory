# AM-113 — Codex Workflow Guardrails

## Objective

Add the smallest project-local Codex extension layer that improves safe,
evidence-first development of Alex Memory without replacing the existing Python
quality harness or exposing private source data.

## Current and target state

The project already has `uv`, Ruff, MyPy, pytest, pre-commit, focused Codex
skills, review roles, and destructive-command rules. Codex CLI 0.146.1 has
stable plugin and hook support, but no project hook configuration or skills for
the memory pipeline, SQLite, async workers, LLM evaluations, or evidence-based
removal.

The target keeps that baseline and adds only distinct plugins, six compact
project skills, and local hooks. Hooks provide workflow feedback only; the
repository sandbox, tests, review, and SQLite practices remain the actual
boundaries.

## Constraints

- Never read, print, copy, commit, or modify `.env`, live SQLite archives,
  Telegram sessions, media, logs, or backups.
- Preserve uncommitted work and do not initialize or change a remote.
- Do not install a plugin whose capability overlaps an existing harness tool or
  has no concrete project use.
- No live Telegram authentication and no production-database test writes.
- Remove code only after source, caller, test, and configuration references
  show that it is obsolete.

## Affected areas

Codex profile plugin registrations, `.codex/hooks.json`, `.codex/hooks/`,
`.agents/skills/`, `Makefile`, `scripts/dev_tools.py`, quality documentation,
task tracking, change records, and this plan. No application schema or source
evidence is in scope.

## Implementation sequence

1. Verify official current hook/plugin syntax and the installed Codex version.
2. Compare requested extensions with the repository baseline and install only
   distinct, compatible capabilities.
3. Add skills and hook scripts with safe, bounded inputs and clear failure
   messages.
4. Validate hooks and skills, then use Plugin Eval on major additions.
5. Audit legacy and duplicate-code candidates from caller/reference evidence;
   remove only items proven obsolete.
6. Document commands, outcomes, limits, and rejected integrations.

## Risks and decisions

- Context7 begins a new Codex thread after installation, so its capability is
  treated as available after a restart rather than as hidden current context.
- Post-tool checks run only for edited maintained Python files; the full gate
  remains `make check` / `make verify`.
- The Stop hook asks for verification evidence only when the assistant claims
  a change; it avoids a loop on continuation turns.
- No committed Git baseline exists, so hook diff review can report structural
  cues but cannot claim a clean source diff until the owner creates an initial
  commit.

## Validation plan

Validate JSON and hook sample-event behavior; compile hook scripts; run Ruff
and MyPy on changed maintained Python; validate skills; inspect Plugin Eval
analysis and benchmark plans; run source/caller reference searches and the
project review signal. Record any incomplete full-suite evidence explicitly.

## Progress and discoveries

- 2026-08-24: Official Codex hook documentation confirms project-local
  `.codex/hooks.json`, `SessionStart`, `PreToolUse`, `PostToolUse`, and `Stop`
  events. CLI 0.146.1 reports hooks and plugins as stable.
- 2026-08-24: Installed Plugin Eval, Codex Security, Context7, four focused
  Trail of Bits marketplace skills, and the curated Python simplifier.
- 2026-08-24: Plugin Eval scored all six project skills A/100 after explicit
  trigger metadata. Codex Security scored F/8 because of high instruction cost
  and a broken relative link, so it was removed; the distinct Trail of Bits
  skills remain on-demand. Live Plugin Eval runs were not used because its
  isolated runner copies Codex authentication/configuration into a temporary
  home, which conflicts with the no-secrets constraint.
- 2026-08-24: The audit removed one unused runtime-status binding and restored
  two missing UI imports. Legacy/compatibility paths remain because migrations,
  configuration, tests, or callers still reference them.

## Final outcome

Completed on 2026-08-24. Codex CLI 0.146.1 now has a compact project-local
workflow layer: six skills, four hook events, and a hook self-check command.
The retained profile extensions are distinct and on-demand; Codex Security,
GitHub, OpenAI Developers, Compound Engineering, CodeRabbit, Sentry, and
overlapping Trail of Bits choices were not retained. No migration or data
action occurred.

The hook harness, skill validation, Plugin Eval static analysis, 13 UI tests,
Ruff, formatting, MyPy, and compilation pass. The complete `make check` gate
still stalls in the existing AI-router suite and was interrupted after 90
seconds without a reported failure. A future live Plugin Eval benchmark needs
a runner that does not copy Codex credentials/configuration to a temporary
home.
