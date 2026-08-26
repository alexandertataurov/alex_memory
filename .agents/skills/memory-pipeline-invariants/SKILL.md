---
name: memory-pipeline-invariants
description: Use when changing Alex Memory ingestion, AI projection, context, or intelligence code; preserve evidence, temporal, authority, boundedness, and failure-isolation invariants.
---

# Memory Pipeline Invariants

Use this skill for any change that can move information from Telegram evidence
through observations, canonical projection, temporal context, or retrieval.

Before editing, read the relevant portions of `docs/ARCHITECTURE.md`,
`docs/DATA_MODEL.md`, `docs/AI_PIPELINE.md`, and `docs/QUALITY.md`. Trace both
the writer and every affected reader; state whether the change affects raw
evidence, observations, canonical state, a derived projection, or a bounded
context package.

Keep these rules true:

- Raw evidence is immutable and traceable; model interpretation never replaces
  it.
- A changed temporal fact closes the old validity interval rather than
  rewriting historical state.
- Manual correction and review authority outrank automated inference.
- AI output is untrusted until locally validated against exact source evidence.
- Deterministic IDs, dates, joins, quotas, and scoring belong in Python or SQL,
  not an LLM prompt.
- Queues, SQL queries, retrieval, and provider context remain explicitly
  bounded.
- Provider failure cannot stop Telegram persistence or represent partial work
  as success.

Use temporary databases and synthetic evidence in tests. Exercise the success,
validation-rejection, provider-failure, retry, and idempotency paths relevant to
the edit. Finish by checking callers and documenting whether a migration,
backfill, or derived-state rebuild is required; do not run any live data action
without explicit operator approval.
