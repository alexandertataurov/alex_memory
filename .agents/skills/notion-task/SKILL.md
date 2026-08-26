---
name: notion-task
description: Find and, when authorized, update the existing Notion task that corresponds to current work while preventing duplicate tasks.
---

# Notion task workflow

Identify the current task from the user request, `TASKS.md`, or active plan.
Search for its exact identifier and distinctive title before considering a new
task. Retrieve only likely matches and check project, status, and scope. If a
task exists, update that object only when the user has authorized a durable
write; otherwise report the match. Create a task only when no suitable object
exists and the user explicitly wants a durable task recorded.
