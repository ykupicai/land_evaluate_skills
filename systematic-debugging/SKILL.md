---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## When to Use

ANY technical issue: test failures, production bugs, unexpected behavior, performance problems, build failures, integration issues.

Use ESPECIALLY when:
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried fixes that didn't work
- You don't fully understand the issue

Don't skip because the issue seems simple (simple bugs have root causes too) or because someone wants it fixed NOW (systematic is faster than thrashing).

## The Four Phases

You MUST complete each phase before proceeding to the next.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully**
   - Don't skip past errors or warnings - they often contain the exact solution
   - Read stack traces completely; note line numbers, file paths, error codes

2. **Reproduce Consistently**
   - Can you trigger it reliably? What are the exact steps?
   - If not reproducible → gather more data, don't guess

3. **Check Recent Changes**
   - Git diff, recent commits, new dependencies, config changes, environmental differences

4. **Gather Evidence in Multi-Component Systems**

   **WHEN system has multiple components (CI → build → signing, API → service → database), BEFORE proposing fixes, add diagnostic instrumentation:**
   ```
   For EACH component boundary:
     - Log what data enters and exits the component
     - Verify environment/config propagation
     - Check state at each layer

   Run once to gather evidence showing WHERE it breaks
   THEN analyze evidence to identify failing component
   THEN investigate that specific component
   ```

   **Example (multi-layer system):**
   ```bash
   # Layer 1: Workflow
   echo "=== Secrets available in workflow: ==="
   echo "IDENTITY: ${IDENTITY:+SET}${IDENTITY:-UNSET}"

   # Layer 2: Build script
   echo "=== Env vars in build script: ==="
   env | grep IDENTITY || echo "IDENTITY not in environment"

   # Layer 3: Signing script
   echo "=== Keychain state: ==="
   security list-keychains
   security find-identity -v

   # Layer 4: Actual signing
   codesign --sign "$IDENTITY" --verbose=4 "$APP"
   ```

   **This reveals:** Which layer fails (secrets → workflow ✓, workflow → build ✗)

5. **Trace Data Flow**

   **WHEN error is deep in call stack:** see `root-cause-tracing.md` in this directory for the complete backward tracing technique.

   **Quick version:** Where does the bad value originate? What called this with it? Keep tracing up to the source. Fix at source, not at symptom.

### Phase 2: Pattern Analysis

**Find the pattern before fixing:**

1. **Find Working Examples** - Locate similar working code in the same codebase
2. **Compare Against References** - If implementing a pattern, read the reference implementation COMPLETELY. Don't skim - read every line
3. **Identify Differences** - List every difference between working and broken, however small. Don't assume "that can't matter"
4. **Understand Dependencies** - What components, settings, config, environment does this need? What assumptions does it make?

### Phase 3: Hypothesis and Testing

**Scientific method:**

1. **Form Single Hypothesis** - State clearly and specifically: "I think X is the root cause because Y." Write it down
2. **Test Minimally** - SMALLEST possible change to test the hypothesis. One variable at a time. Don't fix multiple things at once
3. **Verify Before Continuing** - Worked? → Phase 4. Didn't? → form NEW hypothesis. DON'T add more fixes on top
4. **When You Don't Know** - Say "I don't understand X". Don't pretend to know. Ask for help. Research more

### Phase 4: Implementation

**Fix the root cause, not the symptom:**

1. **Create Failing Test Case**
   - Simplest possible reproduction; automated test if possible, one-off script if no framework
   - MUST have before fixing
   - Use the `superpowers:test-driven-development` skill for writing proper failing tests

2. **Implement Single Fix**
   - Address the root cause identified. ONE change at a time
   - No "while I'm here" improvements, no bundled refactoring

3. **Verify Fix**
   - Test passes now? No other tests broken? Issue actually resolved?

4. **If Fix Doesn't Work**
   - STOP. Count: how many fixes have you tried?
   - If < 3: Return to Phase 1, re-analyze with new information
   - **If ≥ 3: STOP and question the architecture (step 5 below).** DON'T attempt Fix #4 without architectural discussion

5. **If 3+ Fixes Failed: Question Architecture**

   **Pattern indicating architectural problem:**
   - Each fix reveals new shared state/coupling/problem in a different place
   - Fixes require "massive refactoring" to implement
   - Each fix creates new symptoms elsewhere

   **STOP and question fundamentals:**
   - Is this pattern fundamentally sound, or are we "sticking with it through sheer inertia"?
   - Should we refactor the architecture vs. continue fixing symptoms?

   **Discuss with your human partner before attempting more fixes.** This is NOT a failed hypothesis - this is a wrong architecture.

## Red Flags - STOP and Return to Phase 1

| Excuse / thought | Reality |
|------------------|---------|
| "Quick fix for now, investigate later" | First fix sets the pattern. Do it right from the start. |
| "Just try changing X and see if it works" / "It's probably X" | Seeing symptoms ≠ understanding root cause. Stop guessing. |
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Add multiple changes, run tests" | Can't isolate what worked. Causes new bugs. One variable at a time. |
| "Skip the test, I'll manually verify" / "test after fix works" | Untested fixes don't stick. Test first proves it. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I don't fully understand but this might work" | Say so, research, ask. Don't pretend to know. |
| "Here are the main problems: [fixes without investigation]" | Proposing solutions before tracing data flow. |
| **"One more fix attempt" (after 2+ failures)** | 3+ failures = architectural problem. Question the pattern (Phase 4.5), don't fix again. |

**ALL of these mean: STOP. Return to Phase 1.**

## your human partner's Signals You're Doing It Wrong

**Watch for these redirections:**
- "Is that not happening?" - You assumed without verifying
- "Will it show us...?" - You should have added evidence gathering
- "Stop guessing" - You're proposing fixes without understanding
- "Ultra-think this" - Question fundamentals, not just symptoms
- "We're stuck?" (frustrated) - Your approach isn't working

**When you see these:** STOP. Return to Phase 1.

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, gather evidence | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare | Identify differences |
| **3. Hypothesis** | Form theory, test minimally | Confirmed or new hypothesis |
| **4. Implementation** | Create test, fix, verify | Bug resolved, tests pass |

## When Process Reveals "No Root Cause"

If systematic investigation reveals the issue is truly environmental, timing-dependent, or external:

1. You've completed the process
2. Document what you investigated
3. Implement appropriate handling (retry, timeout, error message)
4. Add monitoring/logging for future investigation

**But:** 95% of "no root cause" cases are incomplete investigation.

## Supporting Techniques

Available in this directory:

- **`root-cause-tracing.md`** - Trace bugs backward through call stack to find original trigger
- **`defense-in-depth.md`** - Add validation at multiple layers after finding root cause
- **`condition-based-waiting.md`** - Replace arbitrary timeouts with condition polling
- **`find-polluter.sh`** - Bisect test files to find which test creates unwanted files/state

**Related skills:**
- **superpowers:test-driven-development** - For creating failing test case (Phase 4, Step 1)
- **superpowers:verification-before-completion** - Verify fix worked before claiming success

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common
