---
name: legacy-removal
description: Use when removing Alex Memory legacy or duplicated behavior; require caller, persistence, configuration, documentation, and test evidence first.
---

# Legacy Removal

Use this skill when proposing removal of legacy, compatibility, duplicate, or
dead code.

Establish proof before deletion: find imports and dynamic lookup paths, command
and configuration references, persistence/schema coupling, documented support,
tests, and external entry points. A name search alone is not proof. For a
non-obvious removal, create or update an ExecPlan and state a falsifiable
obsolete-behavior claim.

Delete the smallest complete path: implementation, imports, tests, docs,
configuration, and task references that only supported that path. Never delete
raw evidence, migrations, or history merely to simplify a current projection.
Keep a compatibility path only when a real caller or persisted contract
requires it, and make its scope and sunset condition explicit.

Verify zero intended references, relevant caller behavior, error paths, and
the proportional quality gate. Report what evidence proved obsolescence, what
was removed, migration impact (normally none), and any deliberately retained
compatibility.
