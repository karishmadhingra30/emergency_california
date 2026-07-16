---
name: update-claude-md
description: Update the project CLAUDE.md handoff doc after decisions are made, milestones land, or scope changes. Use whenever a design choice is confirmed by Karishma, a build stage completes, a definition-of-done item is checked off, or something marked "settled" is deliberately changed — so CLAUDE.md always reflects the true current state of the project.
---

# Update CLAUDE.md

CLAUDE.md in the repo root is the living handoff document for this project.
It must always be accurate enough that a fresh session (or a fresh engineer)
can take over from it alone. This skill defines how to keep it that way.

## When to update

Update CLAUDE.md immediately after any of these, in the same turn:

1. **A decision is confirmed by Karishma** — repo layout, schema change,
   dependency added, design choice resolved. Record the decision AND the
   one-line reason.
2. **A milestone lands** — a Track A/B component works end-to-end, a
   definition-of-done item passes, a stage (0/1/2/3) completes.
3. **Scope changes** — something moves between "build now" / "deferred" /
   "non-goal", or something marked "settled" is deliberately revisited
   (only with Karishma's explicit sign-off — never relitigate settled
   items yourself).
4. **New external facts** — gold set delivered, rubric delivered, content
   vetted by a clinician, validation-call feedback received.

## How to update

- **Edit in place; don't append a changelog.** The doc describes current
  state, not history. Git history is the changelog.
- Keep the existing section structure. Add a `## Status` section near the
  top (create it on first update) with: current stage, what works, what's
  next, last-updated date (absolute, e.g. 2026-07-16).
- When a "build now" item is done, mark it done in place and move any
  follow-on work into "What comes after".
- When a decision resolves an open question, delete the question and state
  the decision where the question was. Stale open questions are worse than
  none.
- Preserve the voice: terse, direct, no filler. Non-goals and settled
  decisions stay explicitly labeled as such.
- Never remove: the non-goals list, the offline inviolable constraint
  ("no network call on any emergency-time path"), the content-vetting
  caveat, or the NOT-MEDICAL-ADVICE requirement.

## After editing

Show Karishma a 2–3 line summary of what changed in CLAUDE.md. Commit the
CLAUDE.md change together with the code change it documents (same commit),
not as a separate drive-by commit.
