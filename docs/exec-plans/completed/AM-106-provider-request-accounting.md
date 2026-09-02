# AM-106 — Physical Provider Request Ownership

## Objective

Make the router the single owner of physical provider-request retries, pacing,
attempt accounting, transmitted-input estimates, and normalized usage for both
extraction and grounded answers.

## Boundaries

- Providers perform exactly one transport attempt and return typed failures or
  normalized usage; they do not sleep, retry, or update quota state.
- The router checks availability, records each physical attempt once, applies
  model-specific pacing/retry policy, and records success or failure once.
- Input estimates include the system instruction, provider-required JSON/schema
  instructions, and user prompt actually transmitted. No prompts are stored.
- Tests use fakes and temporary SQLite only; no provider, archive, or live
  database action is permitted.

## Steps

1. Introduce a provider-neutral one-attempt result/request boundary, including
   answer usage, and remove provider-local retry and pacing loops.
2. Move retry/pacing and per-attempt quota/event accounting into the router for
   extraction and answers, preserving timeout/cancellation semantics from AM-105.
3. Normalize Gemini and Groq usage metadata; derive transmitted-input estimates
   from the shared prompt construction rather than raw batch text alone.
4. Add temporary-SQLite/fake tests for first success, retries, failures, RPM/TPM
   guards, answer usage, Groq usage, and no-double-counting.
5. Update task/docs/changelog and verify focused suites, static checks, docs,
   and diff hygiene.

## Completion criteria

Every actual API call has one router-owned attempt record and one policy path;
provider retries, hidden pacing, and zeroed answer usage are absent.

## Result — 2026-08-26

Completed without a migration, replay, backfill, or live provider operation.
Providers now execute one cancellable transport attempt and return normalized
analysis/answer usage. The router records and paces each physical attempt,
estimates transmitted system/schema/user content, and owns bounded retry/fallback
decisions. A Groq timeout whose cancellation cannot be confirmed is recorded as
one failed physical attempt and cannot start an overlapping fallback.
