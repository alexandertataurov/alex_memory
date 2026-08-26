---
name: ai-reliability-change
description: Change Alex Memory AI prompts, model routing, extraction validation, or AI jobs without weakening evidence, boundedness, or provider-failure isolation.
---

Use this skill for changes in `src/alex_memory/ai/`, prompt assembly, semantic
classification, or AI-driven projection.

1. Read `AGENTS.md`, `docs/AI_PIPELINE.md`, and the relevant router, provider,
   repository, validation, and tests. Check current provider/model APIs from
   official documentation when changing an integration or model capability.
2. Keep deterministic matching, dates, IDs, joins, quotas, and state changes
   local. Treat prompts, retrieved Telegram text, tool output, and model output
   as untrusted. Context is background only, never newly inferred evidence.
3. Preserve bounded input, schema validation, source-message validation,
   idempotent persistence, cancellation, timeouts, and diagnostics. Provider or
   quota failure must not halt Telegram archiving or claim work as complete.
4. Add tests for the successful route, output rejection, fallback/failure,
   retry or restart behavior, and absence of duplicate side effects as the
   change warrants. Add an ExecPlan for routing/model migrations or durable
   projection changes.

Report the provider/model API evidence, output contract, failure behavior,
boundedness limits, and verified routes.
