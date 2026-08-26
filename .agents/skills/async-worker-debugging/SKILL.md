---
name: async-worker-debugging
description: Use when debugging Alex Memory Telegram or AI asynchronous work; preserve bounded queues, cancellation-safe ownership, and provider-failure isolation.
---

# Async Worker Debugging

Use this skill when diagnosing Telegram sync, the SQLite writer queue, AI jobs,
provider timeouts, retries, shutdown, or duplicate asynchronous work.

Start with a reproducible synthetic case. Trace the complete ownership path:
producer, queue/claim, durable state transition, provider call, persistence,
retry/cancellation, and shutdown. Record the exact state before and after each
transition; do not infer concurrency behavior from a UI symptom alone.

Check that work is bounded, claimed once, cancellable where the underlying API
allows it, and safe when cancellation cannot stop a blocking SDK call. One
physical provider request must be accounted for exactly once. Provider,
quota, transport, validation, and storage failures have different recovery
domains; no one failure may stop Telegram ingestion.

Use temporary SQLite databases and fakes—never real Telegram credentials or
the production archive. Add focused tests for duplicate claims, timeout,
cancellation, restart/resume, retry backoff, partial persistence, and graceful
shutdown as relevant. Do not add a generic manager or wrapper until an actual
shared ownership contract is demonstrated.
