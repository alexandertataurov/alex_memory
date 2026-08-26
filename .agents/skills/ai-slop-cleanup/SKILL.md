---
name: ai-slop-cleanup
description: Use when cleaning unnecessary generic abstractions, duplicated state, placeholder behavior, or speculative code in Alex Memory.
---

# AI Slop Cleanup

Use this skill for an evidence-based cleanup of unnecessarily generated or
duplicated code.

Look for a concrete cost first: duplicate writers, unused public parameters,
dead compatibility branches, placeholder success paths, broad exception
swallowing, copied derived state, generic managers/factories/wrappers, or
unbounded convenience queries. Trace the authoritative writer and its
consumers before simplifying it. Prefer one explicit contract over a new
abstraction layer.

Do not call code "slop" solely because it is verbose, unfamiliar, or lacks a
unit test. Preserve source evidence, temporal validity, manual authority,
boundedness, and provider-failure isolation. If deletion is not locally
proven, record the evidence gap rather than guessing.

Make the smallest safe edit, remove now-unneeded imports/tests/docs together,
and run caller and failure-path tests. Finish with a diff review for new
placeholder behavior, generic layers, legacy aliases, and competing writers.
