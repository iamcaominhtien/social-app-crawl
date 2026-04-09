---
name: work-logging
description: "Agent must log work to the active Kanban ticket using the Kanban MCP work log tool after completing meaningful steps, for transparency, maintainability, and continuity. Applies to all agents and all files. Also: report bugs found in SKILLS or MCP tools as Kanban bug tickets."
applyTo: "**"
---

# Work Logging & Transparency

## When Working on a Kanban Ticket

After each meaningful step, add a work log entry to the ticket using the Kanban MCP `add_work_log` tool via the `kanbander` agent — **not** by appending to the ticket description.

- Use ISO datetime format (date + 24h time, local timezone), identify the agent by name, 1–2 sentences per entry
- Delegate via: `Use the kanbander agent to add a work log to ticket #N: <what was done and why>`

## When NOT on a Kanban Ticket

No logging needed — skip entirely.

## Bugs in SKILLS or MCP Tools

If a SKILL or MCP tool behaves unexpectedly, create a bug ticket via kanbander:

```
Title: [BUG] <SkillOrTool>: <short description>
- Attempted: ...
- Actual: ...
- Expected: ...
```

Then continue with a workaround if possible.
