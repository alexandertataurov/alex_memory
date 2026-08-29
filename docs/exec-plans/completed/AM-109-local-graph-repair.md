# AM-109 — Local graph repair

## Objective

Prevent deterministic graph repair from turning old or ambiguous chat context
into current canonical project links.

## Current and target state

Repair previously treated all project-linked tasks in a chat as one consensus.
Two historic anchors could link a later orphan task, event, or fact. It also
kept derived links current after their task/event support changed.

Target: automatic repair uses exactly one project supported by at least two
distinct source-message anchors within 90 days of the candidate record. A
single local anchor creates only a Review candidate; competing or stale anchors
create neither a canonical link nor a suggested project. Derived links close
their validity interval when supporting task/event state is corrected or local
fact support disappears.

## Constraints

- Never inspect or alter production data; all verification uses temporary SQLite.
- Do not infer identity, replay historical observations, or backfill links.
- Manual Review decisions stay authoritative and are not removed by repair.
- Targeted repair must not run global temporal-fact interval repair.

## Validation

Focused fixtures prove nearby two-source repair, single-anchor Review,
years-apart exclusion, competing-project exclusion, rejected-observation
exclusion, targeted temporal isolation, and temporal supersession for task,
event, and fact relationships. Full partitioned tests, lint, typing, and docs
checks remain required before handoff.

## Outcome

Completed 2026-08-29. Automatic repair is source-message-distinct and bounded
to a 90-day local neighbourhood. It preserves manual Review authority, rejects
manual-rejected source observations, and closes unsupported derived links
instead of retaining stale current graph state. No migration, replay, backfill,
deletion, or live operation ran.
