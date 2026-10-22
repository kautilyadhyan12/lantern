---
name: tests-first
description: Write failing tests for every acceptance criterion in docs/plans/PLAN-<ID>.md, run them, and log the RED run. No implementation. Invoke as "$tests-first <story-id>".
---
The story ID is the text the user typed after `$tests-first`.

1. Read AGENTS.md and the approved PLAN. Work on branch `story/<ID>` (S0.1 and S0.2: `story/M0-boot`).
2. For every AC, write the tests listed in the PLAN's test plan, each marked `@pytest.mark.ac("<AC-ID>")`. Add hypothesis property tests for every pure function in the Design section.
3. Contract tests use recorded cassettes only. At this step the adapter is still a stub, so its contract tests may be RED with `CassetteMiss` — a valid RED reason. Cassettes are recorded later, in `$implement`, once the adapter can make the call. Never hand-write a cassette.
4. Where the code does not exist yet, add the smallest stubs with the PLAN's signatures that raise `NotImplementedError("<ID>: not implemented yet")`, so tests fail on behaviour rather than on imports.
5. Run only the new tests: `uv run pytest <files> -q --tb=line`. Every new test must fail with an AssertionError or NotImplementedError from the code under test — not with ImportError, SyntaxError, collection or fixture errors. A test that already passes is vacuous: fix it, or explain in the Log why it is a legitimate regression guard.
6. Append `### RED run <date>` under the PLAN's `## Log`: the command, the counts, and a table of failures grouped by reason.
7. Run `uv run python scripts/check_acceptance_ids.py <ID> --backlog docs/06_ROADMAP_BACKLOG.md` and fix any gap. During S0.1 and S0.2 the script does not exist yet: say so in the report instead.
8. Commit tests and stubs (`<ID>: failing tests for <topic>`) and push the branch (`git push -u origin HEAD`). Report in plain English and stop.
