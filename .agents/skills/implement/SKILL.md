---
name: implement
description: Implement a story until its tests and make check pass, without changing what the tests demand. Use after $tests-first. Invoke as "$implement <story-id>".
---
The story ID is the text the user typed after `$implement`.

1. Read AGENTS.md, the PLAN and its RED run. Work on branch `story/<ID>` (S0.1 and S0.2: `story/M0-boot`).
2. Write the smallest code that makes the tests pass, following the PLAN's Design section and the architecture rules in AGENTS.md (gateways, pure core, refs only, no silent divergence from the docs).
3. Do not weaken tests. If a test is wrong, stop, explain why in plain words, and change it only after the user agrees; log the change in the PLAN.
4. When the adapter can make its calls, ask the user to approve recording the missing cassettes with `uv run python scripts/record_fixture.py tool <tool> <case> --args '<json>'` or `… pytest <test ids>` (needs API keys in Codespaces secrets; uses some free quota; before S1.6 builds the recorder, STOP and ask). Log the recording in the PLAN.
5. Run targeted tests while working, then `make check` until it is green (during S0.1, `make check` is whatever S0.1 itself defines).
6. For stories touching egress, tools, policy, people, capture, rendering, the demo or data retention: run `$security-audit` and fix real findings. For stories with many pure functions: run `$test-audit`. Note findings in the PLAN's Log. These are advisory and never replace `$review`.
7. If behaviour or design changed, update the affected doc and propose a decision record for design changes. Append implementation notes and deviations to the PLAN's Log.
8. Commit (`<ID>: <summary>`) and push (`git push -u origin HEAD`). Report in plain English — what was built, the `make check` summary, anything left open — and stop.
