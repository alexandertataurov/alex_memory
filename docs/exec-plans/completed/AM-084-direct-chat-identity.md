# AM-084 — Direct-chat identity

## Objective

Bind a direct Telegram conversation to its deterministic peer identifier.

## Design

`chat_id` owns a `chat_type=user` conversation before aliases are considered.
A unique explicit username may attach an existing person. A display-name
collision creates a peer-keyed person and a merge review candidate. Mentioned
third parties remain separate from the conversation owner.

## Scope

No migration was needed. The bounded repair helper changes only selected direct
contacts and their derived conversation rows. It is caller-controlled and was
not run against the live database.

## Validation

Temporary-database coverage exercises identity, ambiguity, prompt ownership,
third-party mentions, contact materialization, and bounded repair. `make check`
passed 166 tests, Ruff, formatting, MyPy, and compilation. `make db-check`
reported healthy integrity, foreign keys, and FTS indexes.

## Outcome

Completed 2026-08-24.
