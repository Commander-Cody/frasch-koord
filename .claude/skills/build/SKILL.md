---
name: build
description: Implement a task test-first on one branch and PR, loop it through the pr-reviewer agent (max 4 reviews) until approved, never merge.
argument-hint: <issue number or task description>
disable-model-invocation: true
---

Implement this task: **$ARGUMENTS**

You run an implement → review loop. You write the code; the `pr-reviewer` agent judges it. You finish when the reviewer approves, or after the third review without approval, when you hand the decision to the user.

Hard rules for the whole run:

- **Never merge.** No `gh pr merge`, no auto-merge, no push to `main`. Merging is the user's call.
- **One branch, one PR.** All work goes on the single implementation branch created in phase 2 and into the single PR opened in phase 4. Never open a second branch or PR, and never force-push. If `main` moves and the PR conflicts, merge `origin/main` into the branch.
- Running `/build` authorises creating that branch and PR, pushing to that branch, and creating or commenting on GitHub issues for this task. Anything else outward-facing needs the user's approval first.
- Follow `CLAUDE.md`: deferred work and discovered bugs go into GitHub issues, never TODOs in the code.

## Phase 1 — Clarify, in bulk

1. Resolve the task. If it is an issue number, read it with `gh issue view <N> --comments`. If it is free text, search the open issues for overlaps (`gh issue list --search`).
2. Read the code, docs and domain terms the task touches: `CLAUDE.md`, the relevant READMEs, `docs/project-decisions.md`, and the modules involved.
3. Collect everything the user has to decide before you can build the right thing:
   - ambiguities in the task and gaps between the task and the code as it is
   - important decisions: scope boundaries, behaviour choices, data formats, new dependencies, changes to public interfaces, anything hard to undo
   - the seams under test (the public interfaces the tests will sit on), as the `tdd` skill requires them to be agreed up front
   - if the task as a whole is vague: what the user most likely intends, the realistic options, and a precise proposed task description to confirm or correct
4. Ask all of it in one go. Use `AskUserQuestion` (up to 4 questions per call; send the calls back to back without doing other work in between). Put the recommended option first, marked "(Recommended)". Ask open-ended questions together in one plain message. Don't ask about things that have an obvious conventional answer; decide those and list them later in the summary.
5. Write down the resulting precise task: requirements, decisions made, what is out of scope. If the task is an issue, add this as a comment on it. If not, create an issue with it (or extend the overlapping one). This issue is the spec the reviewer checks against.

If a new ambiguity or a major decision comes up later in the run, stop and ask the user then; don't guess.

## Phase 2 — Branch

Work in a dedicated worktree on a new branch from the up-to-date `origin/main`:

```
git fetch origin
git worktree add -b claude/<short-slug> .claude/worktrees/<short-slug> origin/main
```

If this session already runs in a fresh worktree on its own branch with no commits beyond `origin/main`, use that one instead, but make sure it's updated to the latest state of `origin/main`. Either way, this is the only branch of the run. Note its path; you pass it to the reviewer.

## Phase 3 — Implement test-first

Invoke the `tdd` skill and follow it: vertical slices, red before green, one agreed seam and one test per cycle, tests through public interfaces, no mocking of internal collaborators, no tautological assertions.

Once the behaviour is complete, do a refactoring pass with the tests green: clear names, short functions, coherent modules, no duplication, nothing speculative, consistent with the existing architecture. Keep new code looking like the code around it.

Before any review, every check in `.github/workflows/ci.yml` must pass locally. Read that file for the current list; at the time of writing, from the repo root with Node on `PATH` (`source ~/.nvm/nvm.sh && nvm use "$(cat web/.nvmrc)"`):

- `uv sync --locked`, then `uv run just setup` (once per worktree, and after a lockfile change)
- `uv run just check`: every lint, format, type check and test, Python and web
- `uv run just smoke`: the production build (checked), then the smoke test

Fix failures; never skip, delete or weaken a test to get green. A test may only be removed if removing that functionality is part of the task.

If part of the task turns out to be impossible to do in this task, ask the user before deferring it. Once they agree, record the deferred part in an existing or new GitHub issue and state the reason in the PR description.

## Phase 4 — Open the PR

Commit in logical steps with clear messages, push the branch, and open the PR with `gh pr create`. The description says what changed and why, lists the decisions from phase 1, names deferred work with its issue links, and references the task issue (`Closes #<N>` when the PR completes it).

## Phase 5 — Review loop (at most 4 reviews)

For round = 1, 2, 3, 4:

1. Run the `pr-reviewer` agent in the foreground (`Agent` with `subagent_type: pr-reviewer`, `run_in_background: false`). Give it: the PR number, the task issue number, the worktree path (so it reviews there instead of checking out again), the round number, and from round 2 on the previous round's fix list with how you handled each item.
2. **APPROVED** → go to phase 6.
3. **CHANGES REQUESTED** →
   - after round 4: go to phase 7.
   - otherwise: work through the fix list on the same branch, test-first where behaviour changes (a bug fix starts with a failing test that reproduces it). If you disagree with an item, don't silently skip it: explain why in your reply to the reviewer in the next round, and if it touches a real decision, ask the user. Get every CI check green again, commit, push to the same branch (the PR updates itself), and add a short PR comment listing what this round changed. Then start the next round.

## Phase 6 — Approved: report to the user

Return to the user with:

- **Summary**: 2–3 sentences on what was built.
- **Details**:
  - the PR link and branch
  - changes grouped by module/file, with what each change does
  - the tests added or changed, and the seams they cover
  - the decisions taken (the user's and your own)
  - issues created or updated, including deferred work
  - the number of review rounds, and the main points the reviews caught

End by stating that the PR is ready for the user to merge; do not merge it.

## Phase 7 — Not approved after 4 reviews: escalate

Stop implementing. Tell the user what was done, what the third review still requires (its fix list), which items you disagree with and why, and what keeps recurring across rounds. Then ask with `AskUserQuestion` how to continue, for example: another fix-and-review round, a decision on the disputed points, moving the remaining items into issues and leaving the PR as it is, or stopping. Do what the user decides; the no-merge rule still applies.
