---
name: review
description: Run the independent T3 review of a story in a fresh reviewer session inside a throwaway copy of the repository, then triage the verdict. Use after $prove. Invoke as "$review <story-id> [base-ref]".
---
The story ID (and an optional diff base) is the text the user typed after `$review`.

Before the review
1. Check that the tree is clean and that docs/proofs/PROOF-<ID>.md exists for the current code and ends `RESULT: PASS`. If not, run `$prove` first.
2. Tell the user in one or two sentences what the reviewer will look at hardest for this story (the riskiest ACs, edge cases, and invariants the change touches).
3. Run `make review STORY=<ID>` (add `BASE=<ref>` when the base is not `main`). It takes a while; say so.
   - Before S0.4 has built it (the M0 bootstrap and S0.3), perform the steps of docs/05 §4.1–§4.2 by hand: create the worktree and run `uv sync --frozen` in it; substitute {STORY}, {STORY_SLUG} (lower case, dots → underscores), {ROUND} (1 + number of existing tests/review/test_<STORY_SLUG>_r*_adversarial.py files) and {BASE} in .codex/prompts/t3.md; run the `codex exec` command with `--output-last-message docs/reviews/REVIEW-<ID>.json`; copy back only the new tests/review/ file; delete the worktree. Show the user each command before running it.
4. Never review the work yourself in this session, never edit the prompt, and never edit a REVIEW file.

After the review
5. Read docs/reviews/REVIEW-<ID>.json and check that `head_sha` equals the HEAD that was reviewed (the commit you were on when you started the review).
6. Run the reviewer's tests: `uv run pytest tests/review -q -k <STORY_SLUG>`.
7. Report in plain English: the verdict; each blocker with your assessment (real or not, and why); spec ambiguities as questions for the user; notes worth acting on; anything the reviewer changed outside tests/review/ (it was discarded).
8. Commit the reviewer's new test file and the REVIEW file (`<ID>: add review tests, round <N>`) and push (`git push -u origin HEAD`).
9. If REQUEST_CHANGES: fix the blockers, then `$prove` and `$review` again. Count rounds; after round 3 without APPROVE, stop and propose a split via `$plan`.
   If APPROVE: run `$prove` on the commit that adds the review tests, then propose `$ship`.
