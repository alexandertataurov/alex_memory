# AM-077 project quality

## Objective

Prevent casual labels and near-duplicate names from creating canonical projects
automatically. Qualified, unambiguous records may create projects; plausible
duplicates and uncertain labels go through Review.

## Current state

`_project_ai_batch()` calls `EntityResolver.entity("project", name)` for each
extracted project title and project-name reference. Any nonblank unmatched name
currently creates a canonical row. Exact aliases resolve one row, while alias
ambiguity uses the existing entity-merge Review flow.

## Planned change

1. Add a deterministic admission decision at the existing projection caller.
2. Keep exact aliases idempotent and block casual/event/social labels.
3. Compare qualified names with a bounded set of active projects; duplicate
   candidates enter existing manual merge Review instead of creating a row.
4. Retain `_merge_entities()` as the sole merge authority.
5. Leave existing project rows unchanged.

## Validation

- Qualified project creation, casual-label exclusion, and duplicate Review.
- Exact-alias retry and manual merge reference retention.
- Temporary SQLite fixtures only; no schema change is expected.

## Outcome

Completed 2026-08-29; acceptance repair completed 2026-08-30. The accepted-batch writer now creates a new project only
for a high-confidence project observation accompanied by an explicit
same-batch project reference. All other project names resolve existing aliases
only. The normalized-name comparison now examines every non-merged canonical
project, so a former arbitrary 80-row cutoff and an ambiguous match set cannot
allow a new row. Every detected candidate produces a `project_duplicate`
Review carrying the complete ordered candidate list; manual acceptance links
the source observation to the selected existing project and records its alias.
Existing manual project merge retains source-observation references. No schema
or historical-data work ran.
