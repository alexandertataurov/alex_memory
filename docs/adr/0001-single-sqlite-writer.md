# ADR-0001: Serialize Telegram archive writes through one SQLite writer

Status: Accepted

## Context

Telegram catch-up workers and live event handlers can produce concurrent archive writes. The application database is SQLite in WAL mode, which supports useful read concurrency but still benefits from an explicit, bounded write path.

## Decision

`telegram/writer.py` owns the queued persistence path. Catch-up and live code normalize events and submit them to the bounded queue instead of independently writing archive state. Existing events also preserve message edit and deletion history.

## Consequences

The system avoids competing write transactions and has an explicit backpressure boundary. New ingestion sources should preserve this invariant or provide an equally well-defined persistence serialization strategy. The queue must remain bounded and monitoring must never claim an event persisted before the database operation succeeds.
