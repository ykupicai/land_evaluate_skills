---
name: dispatching-parallel-agents
description: Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies
---

# Dispatching Parallel Agents

## Overview

You delegate tasks to specialized agents with isolated context. They never inherit your session's context or history — you construct exactly what they need, which keeps them focused and preserves your own context for coordination. Independent investigations done sequentially waste time.

**Core principle:** Dispatch one agent per independent problem domain. Let them work concurrently.

## When to Use

**Use when:**
- 3+ test files failing with different root causes, or multiple subsystems broken independently
- Each problem can be understood without context from the others
- No shared state between investigations

**Don't use when:**
- Failures are related (fixing one might fix others) — investigate together first
- Understanding requires seeing the entire system, or you don't know what's broken yet (exploratory debugging)
- Agents would interfere (editing same files, using same resources)

## The Pattern

1. **Identify independent domains.** Group failures by what's broken (e.g., tool approval vs batch completion vs abort). Each domain must be fixable without affecting the others.
2. **Create focused agent tasks.** Each agent gets a specific scope (one test file or subsystem), a clear goal ("make these tests pass"), constraints ("don't change other code"), and an expected output ("summary of what you found and fixed").
3. **Dispatch in parallel.** Issue all dispatches in the same response — multiple dispatch calls in one response run in parallel; one per response = sequential. (In Claude Code, each dispatch is an Agent tool call.)

   ```text
   Subagent (general-purpose): "Fix agent-tool-abort.test.ts failures"
   Subagent (general-purpose): "Fix batch-completion-behavior.test.ts failures"
   Subagent (general-purpose): "Fix tool-approval-race-conditions.test.ts failures"
   ```

4. **Review and integrate.** Read each summary, check for conflicts (did agents edit the same code?), run the full test suite, and spot check — agents can make systematic errors.

## Agent Prompt Structure

Good prompts are **focused** (one problem domain), **self-contained** (all context needed), and **specific about output**:

```markdown
Fix the 3 failing tests in src/agents/agent-tool-abort.test.ts:

1. "should abort tool with partial output capture" - expects 'interrupted at' in message
2. "should handle mixed completed and aborted tools" - fast tool aborted instead of completed
3. "should properly track pendingToolCount" - expects 3 results but gets 0

These are timing/race condition issues. Your task:

1. Read the test file and understand what each test verifies
2. Identify root cause - timing issues or actual bugs?
3. Fix by:
   - Replacing arbitrary timeouts with event-based waiting
   - Fixing bugs in abort implementation if found
   - Adjusting test expectations if testing changed behavior

Do NOT just increase timeouts - find the real issue.

Return: Summary of what you found and what you fixed.
```

## Common Mistakes

**❌ Too broad:** "Fix all the tests" — agent gets lost. ✅ "Fix agent-tool-abort.test.ts"
**❌ No context:** "Fix the race condition" — agent doesn't know where. ✅ Paste error messages and test names
**❌ No constraints:** agent might refactor everything. ✅ "Do NOT change production code" / "Fix tests only"
**❌ Vague output:** "Fix it" — you don't know what changed. ✅ "Return summary of root cause and changes"

## Real Example (2025-10-03 session)

6 test failures across 3 files after major refactoring — abort logic, batch completion, and race conditions were independent domains, so one agent per file:

- Agent 1 (agent-tool-abort.test.ts, 3 timing failures): replaced timeouts with event-based waiting
- Agent 2 (batch-completion-behavior.test.ts, 2 failures): fixed event structure bug (threadId in wrong place)
- Agent 3 (tool-approval-race-conditions.test.ts, 1 failure): added wait for async tool execution to complete

All investigations ran concurrently, zero conflicts, full suite green — 3 problems solved in the time of 1.
