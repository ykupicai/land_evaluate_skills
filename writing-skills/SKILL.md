---
name: writing-skills
description: Use when creating new skills, editing existing skills, or verifying skills work before deployment
---

# Writing Skills

## Overview

**Writing skills IS Test-Driven Development applied to process documentation.**

You write test cases (pressure scenarios with subagents), watch them fail (baseline behavior), write the skill, watch tests pass (agents comply), and refactor (close loopholes).

**Core principle:** If you didn't watch an agent fail without the skill, you don't know if the skill teaches the right thing.

**Personal skills live in `~/.claude/skills/`** — see [claude-code-tools.md](../using-superpowers/references/claude-code-tools.md) for details.

**REQUIRED BACKGROUND:** You MUST understand superpowers:test-driven-development. It defines the RED-GREEN-REFACTOR cycle this skill adapts to documentation.

**Official guidance:** anthropic-best-practices.md covers Anthropic's authoring best practices in depth — conciseness targets, description crafting, progressive disclosure. This skill states each rule once and defers detail there.

## What is a Skill?

A **skill** is a reference guide for proven techniques, patterns, or tools — reusable across projects. Skills are NOT narratives about how you solved a problem once.

**Types:** Technique (concrete steps: condition-based-waiting, root-cause-tracing), Pattern (way of thinking: flatten-with-flags, test-invariants), Reference (API/syntax/tool docs).

## TDD Mapping for Skills

| TDD Concept | Skill Creation |
|-------------|----------------|
| **Test case** | Pressure scenario with subagent |
| **Production code** | Skill document (SKILL.md) |
| **Test fails (RED)** | Agent violates rule without skill (baseline) |
| **Test passes (GREEN)** | Agent complies with skill present |
| **Refactor** | Close loopholes while maintaining compliance |
| **Write test first** | Run baseline scenario BEFORE writing skill |
| **Watch it fail** | Document exact rationalizations agent uses |
| **Minimal code** | Write skill addressing those specific violations |
| **Refactor cycle** | Find new rationalizations → plug → re-verify |

## When to Create a Skill

**Create when:** technique wasn't intuitively obvious, you'd reference it again across projects, pattern applies broadly, others would benefit.

**Don't create for:** one-off solutions, standard practices well-documented elsewhere, project-specific conventions (put in your instructions file), or mechanical constraints (if it's enforceable with regex/validation, automate it — save documentation for judgment calls).

## File Organization

```
skills/
  skill-name/
    SKILL.md              # Main reference (required)
    supporting-file.*     # Only if needed
```

**Flat namespace** — all skills in one searchable namespace.

**Separate files only for:**
1. **Heavy reference** (100+ lines) — e.g. `pptx/` with 600-line API reference, XML structure doc, scripts/
2. **Reusable tools** — scripts, utilities, templates — e.g. `condition-based-waiting/example.ts`

**Keep inline:** principles, concepts, code patterns (<50 lines), everything else. Self-contained skills need only SKILL.md.

## SKILL.md Structure

**Frontmatter (YAML):**
- Two required fields: `name` and `description` (see [agentskills.io/specification](https://agentskills.io/specification) for all supported fields); max 1024 characters total
- `name`: letters, numbers, and hyphens only (no parentheses, special chars)
- `description`: third-person, describes ONLY when to use — see SDO below; keep under 500 characters if possible

```markdown
---
name: Skill-Name-With-Hyphens
description: Use when [specific triggering conditions and symptoms]
---

# Skill Name

## Overview
What is this? Core principle in 1-2 sentences.

## When to Use
[Small inline flowchart IF decision non-obvious]
Bullet list with SYMPTOMS and use cases
When NOT to use

## Core Pattern (for techniques/patterns)
Before/after code comparison

## Quick Reference
Table or bullets for scanning common operations

## Implementation
Inline code for simple patterns
Link to file for heavy reference or reusable tools

## Common Mistakes
What goes wrong + fixes

## Real-World Impact (optional)
Concrete results
```

## Skill Discovery Optimization (SDO)

Future agents need to FIND your skill. Your agent reads the description to decide which skills to load — make it answer: "Should I read this skill right now?"

### 1. Description = When to Use, NOT What the Skill Does

Start with "Use when..." and describe ONLY triggering conditions. **NEVER summarize the skill's process or workflow.**

**Why:** Testing revealed agents may follow the description instead of reading the skill body. A description saying "code review between tasks" caused an agent to do ONE review, though the skill's flowchart required TWO. Changing it to just "Use when executing implementation plans with independent tasks" made the agent read and follow the flowchart. Workflow summaries create a shortcut agents will take.

```yaml
# ❌ BAD: Summarizes workflow - agents follow this instead of reading skill
description: Use when executing plans - dispatches subagent per task with code review between tasks

# ❌ BAD: Mentions technology but skill isn't specific to it
description: Use when tests use setTimeout/sleep and are flaky

# ✅ GOOD: Starts with "Use when", describes problem, no workflow
description: Use when tests have race conditions, timing dependencies, or pass/fail inconsistently

# ✅ GOOD: Technology-specific skill with explicit trigger
description: Use when using React Router and handling authentication redirects
```

Describe the *problem* (race conditions, inconsistent behavior), not language-specific symptoms — not too abstract ("For async testing") either. Keep triggers technology-agnostic unless the skill itself is technology-specific — then say so explicitly. Write in third person (injected into system prompt), never first person.

### 2. Keyword Coverage

Use words an agent would search for:
- Error messages: "Hook timed out", "ENOTEMPTY", "race condition"
- Symptoms: "flaky", "hanging", "zombie", "pollution"
- Synonyms: "timeout/hang/freeze", "cleanup/teardown/afterEach"
- Tools: actual commands, library names, file types

### 3. Descriptive Naming

Active voice, verb-first; gerunds (-ing) work well for processes. Name by what you DO or the core insight:
- ✅ `creating-skills` not `skill-creation`; `using-skills` not `skill-usage`
- ✅ `condition-based-waiting` > `async-test-helpers`
- ✅ `flatten-with-flags` > `data-structure-refactoring`
- ✅ `root-cause-tracing` > `debugging-techniques`

### 4. Token Efficiency (Critical)

Frequently-referenced skills load into EVERY conversation. Every token counts.

**Targets (check with `wc -w`):** getting-started workflows <150 words each; frequently-loaded skills <200 words total; other skills <500 words.

**Techniques:**
- Move flag/option details to tool `--help`; reference it instead of documenting every flag
- Cross-reference other skills instead of repeating their workflows
- One minimal example per pattern, not several verbose ones
- Don't explain what's obvious from the command

### 5. Cross-Referencing Other Skills

Use skill name only, with explicit requirement markers:
- ✅ `**REQUIRED SUB-SKILL:** Use superpowers:test-driven-development`
- ❌ `See skills/testing/test-driven-development` (unclear if required)
- ❌ `@skills/testing/test-driven-development/SKILL.md` — `@` syntax force-loads files immediately, consuming 200k+ context before you need them

## Flowchart Usage

**Use flowcharts ONLY for:** non-obvious decision points, process loops where you might stop too early, "when to use A vs B" decisions.

**Never for:** reference material (use tables/lists), code examples (markdown blocks), linear instructions (numbered lists), or labels without semantic meaning (step1, helper2).

See `graphviz-conventions.dot` in this directory for graphviz style rules. Render flowcharts to SVG for your human partner with `render-graphs.js`:
```bash
./render-graphs.js ../some-skill           # Each diagram separately
./render-graphs.js ../some-skill --combine # All diagrams in one SVG
```

## Code Examples

**One excellent example beats many mediocre ones.** Choose the most relevant language (testing → TypeScript/JavaScript, system debugging → Shell/Python, data processing → Python). Make it complete, runnable, from a real scenario, commented to explain WHY.

**Don't:** implement in 5+ languages, create fill-in-the-blank templates, write contrived examples. You're good at porting — one great example is enough.

## The Iron Law (Same as TDD)

```
NO SKILL WITHOUT A FAILING TEST FIRST
```

Applies to NEW skills AND EDITS. Write skill before testing? Delete it. Start over.

**No exceptions:** not for "simple additions", "just adding a section", or "documentation updates". Don't keep untested changes as "reference". Don't "adapt" while running tests. Delete means delete.

## Testing All Skill Types

| Type | Examples | Test with | Success criteria |
|------|----------|-----------|------------------|
| **Discipline-enforcing** | TDD, verification-before-completion | Academic questions; pressure scenarios; multiple pressures combined (time + sunk cost + exhaustion); capture rationalizations and add counters | Follows rule under maximum pressure |
| **Technique** | condition-based-waiting, root-cause-tracing | Application scenarios; edge-case variations; missing-information tests | Applies technique to new scenario |
| **Pattern** | reducing-complexity | Recognition scenarios; application; counter-examples (when NOT to apply) | Identifies when/how to apply |
| **Reference** | API docs, command references | Retrieval scenarios; application of found info; gap testing | Finds and correctly applies information |

## Common Rationalizations for Skipping Testing

| Excuse | Reality |
|--------|---------|
| "Skill is obviously clear" | Clear to you ≠ clear to other agents. Test it. |
| "It's just a reference" | References have gaps and unclear sections. Test retrieval. |
| "Testing is overkill" | Untested skills have issues. Always. 15 min testing saves hours. |
| "I'll test if problems emerge" | Problems = agents can't use skill. Test BEFORE deploying. |
| "Too tedious to test" | Less tedious than debugging a bad skill in production. |
| "I'm confident it's good" | Overconfidence guarantees issues. Test anyway. |
| "Academic review is enough" | Reading ≠ using. Test application scenarios. |
| "No time to test" | Deploying untested skills wastes more time fixing later. |

**All of these mean: Test before deploying. No exceptions.**

## Match the Form to the Failure

Before writing guidance, classify the baseline failure. The form that bulletproofs one failure type measurably backfires on another.

| Baseline failure | Right form | Wrong form |
|---|---|---|
| Skips/violates a rule under pressure (knows better, does it anyway) | Prohibition + rationalization table + red flags (see Bulletproofing below) | Soft guidance ("prefer...", "consider...") |
| Complies, but output has the wrong shape (bloated prompt, buried verdict, restated spec) | Positive recipe or contract: state what the output IS — its parts, in order | Prohibition list ("don't restate", "never narrate") |
| Omits a required element from something they already produce | Structural: REQUIRED field or slot in the template they fill in | Prose reminders near the template |
| Behavior should depend on a condition | Conditional keyed to an observable predicate ("if the brief exists, reference it") | Unconditional rule + exemption clauses |

**Why prohibitions backfire on shaping problems:** under a competing incentive ("make the prompt self-contained"), agents negotiate with "don't X". In head-to-head wording tests on dispatch-prompt guidance, the prohibition arm produced clearly more of the unwanted content than the recipe arm (fully separated distributions), and trended worse than even the no-guidance control — micro-test your own case rather than assuming, but never reach for the prohibition by default. A recipe leaves nothing to negotiate: the output matches the stated shape or it doesn't.

**Rules for whichever form you pick:**
- **No nuance clauses.** "Don't X unless it matters" reopens the negotiation — appending a single nuance clause to a winning recipe degraded it from consistent to noisy in the same wording tests. Express a real exception as its own conditional on an observable predicate.
- **Exemption clauses don't scope.** "This limit doesn't apply to code blocks" still suppresses code blocks. If part of the output must be exempt, restructure so the rule can't reach it.

## Bulletproofing Skills Against Rationalization

Discipline-enforcing skills must resist rationalization — agents are smart and find loopholes under pressure. **Scope:** this toolkit is for discipline failures only; for wrong-shaped output or omitted elements, prohibition-based bulletproofing backfires — use Match the Form to the Failure.

**Psychology note:** See persuasion-principles.md for the research foundation (Cialdini, 2021; Meincke et al., 2025) on authority, commitment, scarcity, social proof, and unity.

**Close every loophole explicitly.** Don't just state the rule — forbid specific workarounds:

```markdown
Write code before test? Delete it. Start over.

**No exceptions:**
- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Don't look at it
- Delete means delete
```

**Address "spirit vs letter" arguments** with a foundational principle early: *"Violating the letter of the rules is violating the spirit of the rules."*

**Build a rationalization table** from baseline testing — every excuse agents make goes in, with a Reality column refuting it (see the table above for the format).

**Create a red flags list** so agents can self-check:

```markdown
## Red Flags - STOP and Start Over
- Code before test
- "I already manually tested it"
- "It's about spirit not ritual"
- "This is different because..."

**All of these mean: Delete code. Start over with TDD.**
```

**Update the description with violation symptoms** — when you're ABOUT to violate the rule: `use when implementing any feature or bugfix, before writing implementation code`.

## RED-GREEN-REFACTOR for Skills

Follow the cycle in the TDD mapping table above. **RED:** run pressure scenarios WITHOUT the skill; document choices, verbatim rationalizations, and which pressures triggered violations. **GREEN:** write a minimal skill addressing those specific rationalizations — no extra content for hypothetical cases — and re-run WITH the skill. **REFACTOR:** new rationalization found? Add an explicit counter; re-test until bulletproof.

### Micro-Test Wording Before Full Scenarios

Full pressure-scenario runs are the final gate, but slow per iteration. Verify the wording itself first:

1. **One fresh-context sample per call** — raw API call, or a single-shot subagent. System prompt = the realistic context the guidance will live in (the full skill or prompt template, not the guidance in isolation); user message = a task that tempts the failure.
2. **Always include a no-guidance control.** If the control doesn't exhibit the failure, there is nothing to fix — stop, don't author the guidance.
3. **5+ reps per variant.** Single samples lie.
4. **Manually read every flagged match.** Template echoes and quoted counter-examples masquerade as hits; automated counts overstate both failure and success.
5. **Variance is a metric.** When guidance lands, reps converge on the same shape. Five different interpretations means the wording isn't binding — tighten the form before adding words.

Micro-tests verify wording; they do not replace pressure scenarios for discipline skills.

**Testing methodology:** See [testing-skills-with-subagents.md](testing-skills-with-subagents.md) for writing pressure scenarios, pressure types (time, sunk cost, authority, exhaustion), plugging holes systematically, and meta-testing.

## Anti-Patterns

- ❌ **Narrative example** ("In session 2025-10-03, we found...") — too specific, not reusable
- ❌ **Multi-language dilution** (example-js.js, example-py.py, example-go.go) — mediocre quality, maintenance burden
- ❌ **Code in flowcharts** (`step1 [label="import fs"]`) — can't copy-paste, hard to read
- ❌ **Generic labels** (helper1, step3) — labels should have semantic meaning

## Skill Creation Checklist (TDD Adapted)

**After writing ANY skill, STOP and complete this checklist before moving to the next.** No batching skills without testing each — deploying untested skills = deploying untested code. **Create a todo for EACH item.**

**RED Phase - Write Failing Test:**
- [ ] Create pressure scenarios (3+ combined pressures for discipline skills)
- [ ] Run scenarios WITHOUT skill - document baseline behavior verbatim
- [ ] Identify patterns in rationalizations/failures

**GREEN Phase - Write Minimal Skill:**
- [ ] Name uses only letters, numbers, hyphens (no parentheses/special chars)
- [ ] YAML frontmatter with required `name` and `description` fields (max 1024 chars; see [spec](https://agentskills.io/specification))
- [ ] Description starts with "Use when...", third person, specific triggers/symptoms
- [ ] Keywords throughout for search; clear overview with core principle
- [ ] Address specific baseline failures identified in RED
- [ ] Guidance form matches the failure type (see Match the Form to the Failure)
- [ ] For behavior-shaping guidance: wording micro-tested against a no-guidance control (5+ reps, every flagged match read manually) — N/A for pure reference skills
- [ ] Code inline OR link to separate file; one excellent example (not multi-language)
- [ ] Run scenarios WITH skill - verify agents now comply

**REFACTOR Phase - Close Loopholes:**
- [ ] Identify NEW rationalizations from testing
- [ ] Add explicit counters + rationalization table + red flags list (if discipline skill)
- [ ] Re-test until bulletproof

**Quality Checks:**
- [ ] Small flowchart only if decision non-obvious; quick reference table; common mistakes section
- [ ] No narrative storytelling; supporting files only for tools or heavy reference

**Deployment:**
- [ ] Commit skill to git and push to your fork (if configured)
- [ ] Consider contributing back via PR (if broadly useful)

## Discovery Workflow

How agents find your skill: encounter problem → search skills (grep descriptions) → find SKILL (description matches) → scan overview → read patterns (quick reference) → load example only when implementing. **Optimize for this flow** — put searchable terms early and often.

## The Bottom Line

**Creating skills IS TDD for process documentation.** Same Iron Law: no skill without failing test first. Same cycle: RED (baseline) → GREEN (write skill) → REFACTOR (close loopholes). If you follow TDD for code, follow it for skills.
