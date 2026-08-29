# AM-103 — Diagnostics truthfulness

## Objective

Ensure read-only diagnostics describe only durable, coherent state and do not
invent provider attribution, graph coverage, or route order.

## Root causes

- Coverage counted stale and old-version classification/analysis rows.
- A null provider in failed-batch diagnostics was displayed as Groq.
- Route counts used overlapping predicates and contextual count by subtraction.
- Graph diagnostics reported a percentage derived from unrelated entity and
  task populations.
- History and terminal monitors embedded route text rather than using router
  policy and state.

## Changes

1. Coverage now requires the current classification/analysis versions and a
   non-stale row at every reported lifecycle stage.
2. Failed batches with no provider report `router` attribution.
3. Route categories use one deterministic precedence order; the undefined
   graph percentage is removed.
4. The live History monitor reads a bounded router snapshot. The terminal
   monitor derives eligible routes from the registry and shows the latest
   durable route decision.

## Constraints

All changed queries and displays are read-only. No routing policy, schema,
migration, replay, backfill, or live operation ran.

## Validation and outcome

Focused temporary-SQLite coverage proves stale classification exclusion,
unknown-provider attribution, exclusive route counts, session-eligible route
ordering, and terminal monitor output. Full validation is recorded with the
completion commit.
