# AM-061 — Provider-verified model registry

## Objective

Add provider-verified Groq profiles with local quota admission and retain a
strict separation between internal-memory extraction and tool-using external
research.

## Boundaries

- No provider request, migration, replay, historical conversion, or live action.
- The existing configured Groq route remains the ordinary fallback. The 120B
  profile is eligible only for high-value reasoning workloads.
- Qwen 3.6 is exposed only through explicit ambiguous-reasoning policy.
- Compound Mini is eligible only for an explicit unstructured external-research
  request. No current caller can persist its tool-augmented output.
- Limits use Groq's published Developer-plan values; account-specific limits can
  be lower and remain enforced by provider responses.

## Steps

1. Verify exact IDs, capabilities, and published limits in Groq documentation.
2. Add bounded profiles and token-per-day admission to the router-owned quota
   tracker without changing provider transport ownership.
3. Prove profile scope, local daily-token rejection, exact selected-model
   execution, and Compound Mini's exclusion from internal workloads with fakes
   and temporary SQLite.
4. Update task and routing documentation, run focused and repository gates, then
   record the durable completion in Notion.

## Completion criteria

All requested model IDs are exact, locally guarded where a daily token cap is
published, and Compound Mini cannot be selected by an internal-memory workload.
