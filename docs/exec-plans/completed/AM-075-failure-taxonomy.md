# AM-075 — Failure taxonomy

## Objective

Keep failures scoped to their actual domain: model quota, reachable server,
transport health, or permanent local error.

## Completed increment

`ProviderQuotaError` retains RPM/TPM/RPD/TPD dimension from normalized errors.
The router short-retries only minute-scale quota failures; daily request/token
exhaustion applies a model-local cooldown through the next UTC day. Transport
health remains separate.

Migration 20 adds nullable `ai_jobs.retry_after_at` and an eligible-queue
index. It preserves all source membership and changes only durable derived job
state: existing failed history jobs become pending once, retryable route or
context failures return to pending with capped exponential backoff, and
configuration/response failures remain terminal.

## Constraints and validation

Routing owns retry, pacing, accounting, and fallback. Migration tests preserve
exact job membership; fake-route tests cover quota parsing, typed permanent
errors, temporary route failure, and delayed queue eligibility.

## Remaining work

None. AM-075 is dependency closure; no architecture or model-scope expansion.

## Progress

- 2026-08-27: expired cooldowns now clear from both in-memory quota state and
  the current UTC usage row. Failed history work is already durably reclaimable
  by `claim_ai_jobs`; a future delayed-retry policy needs its own persisted
  scheduling field rather than repurposing a claim timestamp. No schema or
  live action ran.
- 2026-08-27: Gemini now treats a structured HTTP 429 as quota even when its
  text is unhelpful, preferring structured quota ID and retry-delay details
  before its bounded text fallback. Temporary fake-provider coverage proves
  daily-token dimension preservation. No integration, schema, or live action
  ran.
- 2026-08-27: permanent local configuration failures and invalid/empty provider
  responses now have distinct typed errors. Response JSON is rejected before
  persistence and neither category takes a retry path. No schema or live action
  ran.
- 2026-08-27: migration 20 adds a restart-safe retry schedule for history jobs.
  The claim query admits only due pending rows, preserving exact membership and
  preventing terminal failures from automatic reclaim. Temporary SQLite tests
  cover migration preservation, restart/due retry, permanent terminal state,
  and typed all-route temporary failure. No live migration or repair ran.
