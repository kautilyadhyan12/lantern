---
name: ship
description: Push the story branch, open the PR, wait for CI and squash-merge after the user's yes. Invoke as "$ship <story-id>".
---
The story ID is the text the user typed after `$ship`. For the one-time M0 bootstrap use `$ship M0` (branch `story/M0-boot`, PROOF-M0 and REVIEW-M0; docs/08_SETUP.md §5).

1. Preconditions — stop and report if any fails: docs/reviews/REVIEW-<ID>.json says APPROVE; the latest PROOF is for the current code and says `RESULT: PASS`; `git diff --name-only <reviewed_sha> HEAD` lists only files under tests/review/ and docs/.
2. Mark the story done in docs/06_ROADMAP_BACKLOG.md (append " — DONE <date>" to its heading), close the PLAN's Log, commit (`<ID>: mark done`), and push the branch (`git push -u origin HEAD`). Only files under docs/ change here, so the proof and review still apply.
3. Create the PR: `gh pr create --base main --title "<ID>: <title>" --body-file <temp file>` (for M0 the title is `S0.1+S0.2: repository skeleton and proof kit`), filling the repository's PR template (story, summary, AC → tests table, risks, rollback, checklist). Before S0.5 the template does not exist yet: write the same headings by hand.
4. From S0.5 on, watch CI with `gh pr checks <n> --watch` (before CI exists, skip this step and say so). If CI fails: report it in plain words and STOP. Any fix is new code, so it goes through `$implement` → `$prove` → `$review` before `$ship` starts again.
5. Ask the user: "CI is green. Merge PR #<n> into main?" Wait for a yes. Then `gh pr merge <n> --squash --delete-branch --subject "<ID>: <title>"`.
6. `git checkout main`, `git pull --ff-only`, and delete the local story branch.
7. Report in plain English, and suggest `$smoke` if the milestone has a smoke check. Remind the user they can close the tab.
