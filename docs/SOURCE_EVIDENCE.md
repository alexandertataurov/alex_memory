# Source-Neutral Evidence

`EvidenceRecord` is the ingestion boundary for sources beyond Telegram. Every
record has a stable four-part source identity:

```text
source name + source account + conversation ID + source item ID
```

It also preserves occurrence and observation times, author identity, content
type, raw source locator, source metadata, edit time, deletion time, and
deletion state. `EvidenceRepository` stores its latest state in
`source_evidence` and records the prior content in `source_evidence_versions`
whenever an item changes or is deleted.

Telegram remains the original raw-evidence store. `TelegramEvidenceSource`
adapts its `messages` and `message_versions` lifecycle to `EvidenceRecord`
without duplicating the Telegram archive. Task Deep Dive uses this adapter for
task-origin evidence, proving that the common contract is usable by existing
consumers.

Future Gmail, WhatsApp, iMessage, and Drive ingestors should implement the
`EvidenceSource` protocol, preserve their provider-native IDs in both identity
and `raw_locator`, and write to `EvidenceRepository`. They must not flatten
provider IDs into Telegram fields or overwrite a prior evidence state.
