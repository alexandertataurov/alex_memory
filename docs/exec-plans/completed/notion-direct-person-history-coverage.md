# Notion task — Complete direct-person history coverage

## Control-plane status

This is a synchronized implementation plan for Notion task
`3c7f52e9-545b-8199-83cc-eef158d65daa`. Notion controls scope, status, and
completion. The task is active with no owner or operator gate.

## Objective

For one selected canonical direct contact, make every currently eligible
direct-chat message visible as current-version completed work or an explicit
durable pending/running/failed/retryable state. Reuse the existing `profile`
job lane, exact `ai_job_messages` membership, current profile extractor
version, and normal validated processing path.

## Verified gap

`queue_profile_scan()` created only its caller's small window limit. The
remaining eligible direct messages had no profile job membership and therefore
no explicit lifecycle state. Failed profile jobs also remained failed even
though the UI called them retryable; the existing retry claim path accepts only
pending jobs.

## Constraints

- No new scheduler, AI lane, schema, writer, replay, backfill, repair, or live
  operation. Raw messages and immutable source membership remain unchanged.
- Each provider request remains an existing bounded chronological profile
  window; live work keeps its existing priority because this is manual work.
- Only canonical direct-chat ownership and existing allowed self-authored or
  claim-linked context can qualify a message. Existing policy and semantic
  filters remain authoritative.
- Retry changes durable job state only after the owner invokes the selected
  profile scan again. It never fabricates completion or changes job membership.

## Bounded increment

1. Make the explicit selected-person action persist every eligible message as
   exact current-version profile-job membership before it claims at most the
   requested bounded number of windows.
2. Make coverage status partition that eligible set by exact membership:
   completed, pending, running, and failed/retryable. Current analysis and
   profile extractor versions both define membership validity.
3. On a later explicit selected-person action, return a bounded failed set to
   pending before normal claim/processing; membership and evidence never move.
4. Add temporary-SQLite cases for complete coverage, retry transition, both
   version boundaries, exact membership, and read-only status.

## Outcome

The selected profile scan now creates all current eligible direct-history job
windows with immutable `ai_job_messages` membership, then claims only the
requested bounded number for provider work. Status counts are exact
message-level partitions for the current global analysis and profile extractor
versions; failed windows are labelled retryable and re-enter pending only from
another explicit scan. No schema, scheduler, writer, replay, repair, backfill,
or live operation changed.

## Non-goals

This increment does not automatically submit all remaining history, invent
contacts, change global history coverage, add recursive queues, or run any
existing jobs against live data.
