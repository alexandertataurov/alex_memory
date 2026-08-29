# AM-058 — Routing fallback truthfulness

## Objective

Make session fallback selection match the failure domain and keep durable
telemetry truthful when a compatible fallback remains selected.

## Outcome

Only a typed daily quota failure (`rpd` or `tpd`) pins a successful fallback.
Connection, transient, response, and short-term quota failures remain temporary.
Fallback status is compared with the unpinned preferred route, so a pinned
compatible route remains a `session_pinned_fallback` rather than becoming a
false preferred route. Forced overrides retain their separate route kind.

## Constraints and validation

The router remains the sole execution, quota, and telemetry owner. No schema,
migration, provider request, replay, backfill, or live operation ran. Temporary
provider fixtures cover daily pinning, provider health, one-off failure, and
truthful repeated fallback telemetry.
