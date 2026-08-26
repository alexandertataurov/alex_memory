# AM-095 — Read-only Today and terminal workflow

## Objective

Turn the terminal's daily operational path into a discoverable, evidence-first
workflow without allowing reads to silently mutate derived state.

## Current and target state

`attention_items()` invokes follow-up and project-health evaluation before
reading rows, and the menu hides both that view and Follow-ups. Entity and chat
selection stop at alphabetical limits; task/review actions use compact commands
with little evidence preview. Telegram startup failure exits before local
SQLite reads are available.

The target exposes a read-only Today view, an explicit maintenance refresh,
bounded/filterable selectors and task views, evidence drill-down for decisions
and retrieval, focused diagnostics, and a degraded local-read session when
Telegram cannot start.

## Constraints

- Raw messages, accepted AI observations, manual feedback, task locks, and
  temporal facts remain untouched by read paths.
- The explicit refresh may only apply the existing deterministic follow-up and
  project-health projections; it has no provider call and is transactionally
  committed by the caller.
- SQL result sets remain bounded and all UI text stays literal Rich `Text`.
- No schema migration, backfill, or live database action is required.

## Affected modules

- `src/alex_memory/app.py`: startup degradation, commands, confirmations, and
  drill-down routing.
- `src/alex_memory/intelligence.py`: separated read-only attention query and
  explicit operational refresh.
- `src/alex_memory/ui/{navigation,screens,runtime_status}.py`: navigation,
  bounded views, and detail rendering.
- focused temporary-DB UI, intelligence, and lifecycle tests; task/docs/changelog.

## Implementation sequence

1. Split the read query from deterministic derived evaluation and test that
   Today does not write tasks, projects, follow-ups, or notifications.
2. Make Today and Follow-ups visible, add explicit Refresh operational state,
   and bound default tasks to current actionable work with an All escape hatch.
3. Add text-filtered selectors, full review evidence, confirmation before task
   lifecycle mutation, and drill-down of bounded retrieval/Ask sources.
4. Split diagnostic reports into selected subviews and permit a local-only
   session if Telegram setup/start fails after SQLite opens.
5. Verify focused paths plus formatting, types, docs, and no migration.

## Risks and decisions

- Startup failure before SQLite connection remains fatal; only failures after a
  successfully opened local database may degrade to local-read mode.
- The scheduled/background writer remains the long-term owner of freshness;
  this change supplies an explicit operator action until AM-055 moves it to a
  durable scheduler.

## Validation

Use temporary databases and fake Telegram startup failures. Check no read path
changes SQLite state; check explicit refresh is idempotent; confirm bounded
filters/drill-down and manual confirmation; then run focused tests and project
quality commands available in the local environment.

## Progress and discoveries

Completed 2026-08-24.

Final outcome: test and static validation passed.

- 2026-08-24: source audit confirmed `attention_items()` calls both mutating
  evaluators and the home command registry omits its `attention` and
  `follow_ups` aliases. `show_action_inbox()` has no production caller.
