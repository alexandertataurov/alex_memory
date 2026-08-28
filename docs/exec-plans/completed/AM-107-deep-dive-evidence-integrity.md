# AM-107 — Deep Dive evidence integrity

## Objective

Ensure every Deep Dive evidence row has explicit, demonstrable membership in
the investigated task.

## Scope

Expose stable citeable fact IDs. Admit structured events only through exact
task/source linkage or conservative Unicode-aware title matching. Keep broader
context facts as report background, not task evidence. Require raw messages to
contain a task-linked anchor. Preserve the strongest duplicate representation
and merge its provenance reasons.

## Constraints

- Preserve bounded provider-independent Deep Dive behavior.
- Do not alter source, canonical task, session, note, or pin records.
- Do not add a retrieval system or automatic inference.

## Validation

Fact-bearing reports, unlinked and linked events, Unicode titles, raw-anchor
admission, duplicate origin/raw records, lifecycle records, and deterministic
question answers are covered by temporary-SQLite tests.

## Outcome

Completed 2026-08-28. Deep Dive now exposes fact IDs, excludes contextual facts
from task evidence, admits events only through exact links or a conservative
Unicode-aware task-title match, and requires task-linked anchors for raw
messages. Duplicate evidence retains strongest provenance and merged reasons.
