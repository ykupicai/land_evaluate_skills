---
name: grill-me
description: A relentless interview to sharpen a plan or design, then carry it end-to-end through spec, tickets, implementation, and code review.
disable-model-invocation: true
---

# grill-me — full pipeline

Calling this skill runs the full chain: **grilling → to-spec → to-tickets → implement → code-review**. Each stage's own skill defines how that stage works — this file only sequences the handoffs between stages and marks where a human checkpoint is required. Do not skip a stage or its checkpoint just because the next stage is "obvious."

## 0. Tracker fallback

These skills assume `/setup-matt-pocock-skills` has configured an issue tracker. If `docs/agents/issue-tracker.md` (or equivalent) is not found in this repo, don't stop and don't ask — fall back to local files under `.scratch/<feature-slug>/`: the spec goes to `.scratch/<feature-slug>/spec.md`, tickets go to `.scratch/<feature-slug>/issues/<NN>-<slug>.md` using to-tickets' own local-ticket-template, and blocking edges are plain markdown references instead of native tracker links.

## 1. Grill (`grilling`)

Run the `grilling` process in full: interview one question at a time, give a recommended answer for each, resolve every branch of the decision tree.

**Checkpoint — load-bearing, not optional:** do not proceed to step 2 until the user explicitly confirms shared understanding, exactly as `grilling` itself requires.

## 2. Spec (`to-spec`)

Run the `to-spec` process on the confirmed discussion: explore the repo if needed, sketch seams and confirm they match the user's expectations, then write the spec from `to-spec`'s template.

**Checkpoint:** show the drafted spec and get a quick go/no-go before publishing it (to the tracker, or to the local fallback file). This is one confirmation, not a re-run of the grilling interview.

## 3. Tickets (`to-tickets`)

Run the `to-tickets` process against the published/confirmed spec: draft vertical-slice tickets with blocking edges.

**Checkpoint:** quiz the user and iterate until they approve the breakdown, per `to-tickets` step 4 — this gate stays exactly as authored. Publish only after approval.

## 4. Implement (`implement`)

Before writing any code, capture the repo's current `HEAD` (`git rev-parse HEAD`) — this is the fixed point step 5 will diff against.

Then run the `implement` process against the frontier of approved tickets (or the spec directly if no tickets exist): TDD at pre-agreed seams, regular typechecking and test runs. `implement`'s own text already chains to `/code-review` and a commit at the end — follow it as written, in that order, don't skip either.

## 5. Review (`code-review`)

Triggered automatically by `implement`'s last step. Use the `HEAD` captured in step 4 as the fixed point. Report the Standards and Spec axes side by side exactly as `code-review` defines — don't merge or rerank them.

## Stopping early

The user can call a halt at any checkpoint above just by saying so. None of the checkpoints are skippable by default — only by the user's explicit instruction in the moment.
