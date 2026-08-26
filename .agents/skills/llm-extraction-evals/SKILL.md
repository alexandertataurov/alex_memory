---
name: llm-extraction-evals
description: Use when changing Alex Memory LLM extraction, routing, or validation; design source-backed, bounded evaluations.
---

# LLM Extraction Evals

Use this skill for extraction prompts, model routing, output validation,
acceptance thresholds, provider fallbacks, or AI-job behavior.

Define a compact fixture set of source messages and expected validated outcomes
before changing a prompt or routing rule. Include accepted observations,
rejected malformed output, ambiguous identity/review routing, third-party
mentions, temporal assertions, multilingual examples where affected, and
provider failure. Keep fixtures private-safe and synthetic; do not paste live
Telegram evidence or credentials into an evaluation.

Measure the observable contract: source references, validation outcome,
canonical projection, review/manual authority, queue state, selected route,
physical-call accounting, and bounded context size. Separate deterministic
logic into Python or SQL instead of relying on model behavior. Provider output
may be normalized for transport shape but never silently repaired into a more
authoritative semantic result.

Run the smallest focused tests first, then the proportional project gate. Report
the fixture coverage, model-independent acceptance criteria, any provider-free
limitations, and whether historical items require a bounded replay or rebuild.
