# AM-094 — Ask Memory evidence and router pipeline

## Objective

Keep one deterministic retrieval-to-evidence-to-router pipeline for Ask Memory,
with bounded citations, typed router failures, and an offline deterministic
fallback.

## Current and target state

Ask Memory dispatches through `AIRouter`. Remaining defects are a rank-only
evidence slice, an implicit non-citable structured-context boundary, and a
broad fallback catch that hides programming errors alongside classified router
failures.

Target: deterministic presentation remains independent from model evidence.
Evidence selection is bounded by the context budget and balances task,
canonical/observation, summary, and raw-message records when present. Every
citable prompt record has its numbered stable identity; structured context is
explicit background only. Only router/provider failures return the local
answer; unexpected defects stay visible.

## Constraints

- Preserve AIRouter as sole request, quota, retry, health, and telemetry owner.
- Accept model text only when all citations address supplied evidence.
- Do not change persistence, canonical state, or migrations.

## Validation

1. Exercise mixed evidence, waiting-specific selection, citation boundaries,
   successful routed answer, typed router fallback, and unexpected errors.
2. Keep input bounded and retain the local answer when interactive AI is
   disabled or unavailable.

## Outcome

Completed 2026-08-28. Ask Memory uses bounded, balanced evidence selection;
numbered evidence remains the only citable material and structured context is
explicit background. Typed provider failures retain the local deterministic
answer, while unexpected errors remain visible.
