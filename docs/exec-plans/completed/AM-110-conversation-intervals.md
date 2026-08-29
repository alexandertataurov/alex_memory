# AM-110 — Conversation intervals

Completed 2026-08-29. Project and contact conversation periods now share a
90-day inactivity boundary and `[started_at, ended_at)` semantics. A repeated
project after an inactive gap becomes a new period; confidence counts distinct
source-message/item/task anchor identities instead of raw rows. Historical
lookups require the period to be active at the cutoff. No migration, rebuild,
replay, or live operation ran.
