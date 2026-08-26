# Temporal Conflict Review

Non-state temporal facts do not silently replace a different current value. The
incoming value is stored as a pending conflict alongside the current fact, its
valid time, confidence, and originating chat/message/AI-item references. Raw
Telegram evidence remains unchanged.

The terminal **Review** command shows ordinary AI review entries and pending
temporal conflicts. A conflict shows both values and their evidence references.
Choose one of:

- **keep** — resolve the conflict while retaining the current fact;
- **accept** — make the observed value current when it is newer, or retain it as
  a historical fact when its source time predates the current value;
- **ignore** — dismiss the proposed observation without changing canonical state.

An optional decision note, timestamp, resulting fact ID, and selected decision
are appended to `context_conflict_decisions`. This preserves manual correction
history rather than overwriting it. Migration 6, `context_conflict_review`, adds
that decision log and the proposed-observation record used to resolve a conflict.

Pending conflicts from before migration 6 remain visible. If their original
proposal was not stored, **accept** prompts for an explicit manual JSON value and
effective time. That fact is marked `manual`, preserves the old interval, and is
recorded in the same decision history.
