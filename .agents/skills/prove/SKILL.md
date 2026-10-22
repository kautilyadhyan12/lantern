---
name: prove
description: Produce docs/proofs/PROOF-<ID>.md by running the full gate on the current commit. Required before every review and before shipping. Invoke as "$prove <story-id>".
---
The story ID is the text the user typed after `$prove`.

1. Make sure all work is committed: `git status` must show no changes to tracked files outside `docs/`. If it does, commit first.
2. Run exactly `make prove STORY=<ID>` (for the one-time M0 bootstrap: `make prove STORY=M0 AC_STORIES="S0.1 S0.2"`). If the prove tooling does not exist yet (during S0.1 and S0.2), say so, run `make check` instead and report its result; the proof happens in the bootstrap (docs/08_SETUP.md §5).
3. Read docs/proofs/PROOF-<ID>.md. Report in plain English: the RESULT, the commit, test counts, coverage (total and each critical path), and any failed step with its key lines.
4. If RESULT is FAIL: fix the cause — in code, or in a test only when the test itself is wrong and the user agrees (never thresholds, never skips) — commit, and run again.
5. Commit the PROOF file and push (`git push -u origin HEAD`). Never write or edit a PROOF file by hand. Stop after reporting.
