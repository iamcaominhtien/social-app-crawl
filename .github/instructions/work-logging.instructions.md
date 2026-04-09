---
name: work-logging
description: "Agent must log work to the active Kanban ticket using the Kanban MCP work log tool after completing meaningful steps, for transparency, maintainability, and continuity. Applies to all agents and all files. Also: report bugs found in SKILLS or MCP tools as Kanban bug tickets."
applyTo: "**"
---

# Work Logging & Transparency

## When Working on a Kanban Ticket

After each meaningful step, add a work log entry to the ticket using the Kanban MCP `add_work_log` tool directly if available, or via the `kanbander` agent — **not** by appending to the ticket description.

- Timestamps are auto-added by the tool — do not include them manually
- Identify the agent by name, 1–2 sentences per entry describing what was done and why
- Sub-agents (developer, qc, code-change-reviewer, etc.) are expected to self-log after completing their work when the Kanban tool is available to them
- If the Kanban tool is not available, delegate via: `Use the kanbander agent to add a work log to ticket #N: <what was done and why>`

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
