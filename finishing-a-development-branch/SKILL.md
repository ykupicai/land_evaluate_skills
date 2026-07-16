---
name: finishing-a-development-branch
description: Use when implementation is complete, all tests pass, and you need to decide how to integrate the work - guides completion of development work by presenting structured options for merge, PR, or cleanup
---

# Finishing a Development Branch

## Overview

Guide completion of development work by presenting clear options and handling chosen workflow.

**Core principle:** Verify tests → Detect environment → Present options → Execute choice → Clean up.

**Announce at start:** "I'm using the finishing-a-development-branch skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before presenting options, verify tests pass** (`npm test` / `cargo test` / `pytest` / `go test ./...`). Never offer merge/PR options on broken code.

**If tests fail:** Report "Tests failing (<N> failures). Must fix before completing," show the failures, and stop. Don't proceed to Step 2.

### Step 2: Detect Environment

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
```

This determines which menu to show and how cleanup works:

| State | Menu | Cleanup |
|-------|------|---------|
| `GIT_DIR == GIT_COMMON` (normal repo) | Standard 4 options | No worktree to clean up |
| `GIT_DIR != GIT_COMMON`, named branch | Standard 4 options | Provenance-based (see Step 6) |
| `GIT_DIR != GIT_COMMON`, detached HEAD | Reduced 3 options (no merge) | No cleanup (externally managed) |

### Step 3: Determine Base Branch

```bash
git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
```

Or ask: "This branch split from main - is that correct?"

### Step 4: Present Options

Open-ended "what should I do next?" questions are ambiguous — present exactly the structured menu for the detected state, with no added explanation.

**Normal repo and named-branch worktree:**

```
Implementation complete. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

**Detached HEAD:**

```
Implementation complete. You're on a detached HEAD (externally managed workspace).

1. Push as new branch and create a Pull Request
2. Keep as-is (I'll handle it later)
3. Discard this work

Which option?
```

### Step 5: Execute Choice

Never force-push without an explicit user request.

#### Option 1: Merge Locally

```bash
# Get main repo root for CWD safety
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"

# Merge first — verify success before removing anything
git checkout <base-branch>
git pull
git merge <feature-branch>

# Verify tests on merged result
<test command>
```

Only after the merge succeeds and tests pass: clean up the worktree (Step 6), **then** delete the branch — `git branch -d` fails while a worktree still references it:

```bash
git branch -d <feature-branch>
```

#### Option 2: Push and Create PR

```bash
git push -u origin <feature-branch>
```

**Do NOT clean up the worktree** — the user needs it alive to iterate on PR feedback.

#### Option 3: Keep As-Is

Report: "Keeping branch <name>. Worktree preserved at <path>." No cleanup.

#### Option 4: Discard

**Confirm first — require the exact typed word:**
```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>
- Worktree at <path>

Type 'discard' to confirm.
```

If confirmed, `cd` to `$MAIN_ROOT` (as in Option 1), clean up the worktree (Step 6), then force-delete the branch:

```bash
git branch -D <feature-branch>
```

### Step 6: Cleanup Workspace

**Only runs for Options 1 and 4.** Options 2 and 3 always preserve the worktree.

**If `GIT_DIR == GIT_COMMON`:** Normal repo, no worktree to clean up. Done.

**Native tool first:** If your platform provides a workspace-exit tool (e.g., `ExitWorktree`), use it — it returns you to the main checkout and handles worktree removal and registration itself. Skip the manual commands below.

**Manual fallback — check provenance first.** Only clean up worktrees this workflow created (path under `.worktrees/` or `worktrees/`):

```bash
WORKTREE_PATH=$(git rev-parse --show-toplevel)
MAIN_ROOT=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)
cd "$MAIN_ROOT"   # git worktree remove fails silently if CWD is inside the worktree
git worktree remove "$WORKTREE_PATH"
git worktree prune  # Self-healing: clean up any stale registrations
```

**Otherwise:** The host environment (harness) owns this workspace — removing it causes phantom state. Leave it in place.
