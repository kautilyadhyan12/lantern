# PLAN S0.2.1 — Stop removed tests from satisfying requirements

## Goal

Repair the last demonstrated requirement-tracing defect: a test that is
deleted or replaced must not count as evidence that a requirement is tested.
This is a proposed split of the remaining S0.2 repair work after three
unsuccessful joint bootstrap reviews. No implementation is authorized yet.

## Scope

In: the static test-binding check, its negative and allowed-case tests, and
the documentation/verification amendment proposed in ADR 0007. Retain every
existing acceptance criterion and reviewer regression. The new repair story
would join the existing story/M0-boot branch and joint proof under the narrow
bootstrap extension proposed in that ADR.

Out: product features, new dependencies, full Python execution or general
pytest collection emulation, new keys, account settings, paid services,
protected harness/CI changes, PR creation and merging. Approval of this plan
would authorize one additional fresh joint review after repair, not an
unlimited review-budget reset. A merge still requires a separate yes.

## Design

Keep these public interfaces unchanged in scripts/check_acceptance_ids.py:

```python
def acceptance_ids(backlog_text: str, stories: Sequence[str]) -> list[str]: ...
def test_marks(source: str, path: str) -> dict[str, list[str]]: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

Use the parsed AST and module/class namespaces to detect removal or rebinding
of test definitions. Conservatively raise ValueError for ambiguous test
bindings rather than crediting an obsolete definition. Include direct,
annotated, augmented and unpacking assignments, deletion and import aliases
that overwrite a test binding. Function-local bindings must not overwrite
module or other-class test bindings. Preserve the existing duplicate-definition
guard, discoverable filename patterns and unknown-ID detection in helper
files. Never import or execute the inspected modules.

This is a development script, not a new application layer. No Pydantic model,
database data, migration, network path or external schema changes.

Files after approval: the checker; new tests/test_acceptance_bindings.py;
this plan and PLAN-M0; backlog and bootstrap/workflow notes for the approved
split; accepted ADR 0007; sanctioned generated proof/review outputs and only
fresh reviewer test files. Existing reviewer files remain intact. No protected
prompt, schema, skill, hook or review runner changes.

## Acceptance criteria

The existing requirement remains unchanged, copied verbatim from the backlog:

- S0.2-AC3 `scripts/check_acceptance_ids.py <ID> [<ID> …] --backlog <path>` collects the AC IDs listed under each given story's heading in the backlog file, scans `tests/` for `@pytest.mark.ac(...)` without importing test modules, prints an AC → tests table, and fails when one of those ACs has no test or any test anywhere references an AC ID that appears nowhere in the backlog.

### Proposed AC changes

Add the following repair story to the backlog only after approval. These are
proposals; the backlog and original criterion have not been changed:

- S0.2.1-AC1 A marked test deleted or rebound in its module or class cannot satisfy an acceptance criterion; ambiguous bindings are rejected without importing or executing test modules. Cover ordinary, annotated, augmented and unpacking assignments, deletion and import rebinding.
- S0.2.1-AC2 Existing literal-marker validation, unknown-ID detection in every scanned Python file, discoverable-module filtering and namespace isolation remain enforced; all retained review tests pass unchanged.

Approval must cover this proposed split, the bootstrap branch extension and
the single additional joint review in ADR 0007 before new tests or code.

## Test plan

For AC1, retain both RED cases in
tests/review/test_m0_r3_adversarial.py::test_removed_test_does_not_satisfy_acceptance.
Add unit/parameterized tests in tests/test_acceptance_bindings.py for module
and class removal/rebinding, assignment variants and import aliases. Mark new
tests with the proposed repair IDs after they are accepted into the backlog.
Run and record RED before implementation; a correct assertion failure is
required, not a collection error.

For AC2, add allowed cases for unrelated assignments, locals and distinct
classes, plus a generated property that unrelated bindings cannot change a
valid criterion mapping. Run existing acceptance tests and all reviewer files.
Keep the requirement scanner's no-import side-effect trap and helper-file
unknown-ID cases. No cassette, model prompt or eval case applies.

After implementation, commit/push, then run
`make prove STORY=M0 AC_STORIES="S0.1 S0.2 S0.2.1"`. Require the full gate and
all 15 original/proposed criterion IDs. Save the writer output unchanged.
Run one fresh joint reviewer, round 4, using the existing bootstrap procedure
and all criteria; retain its new tests. If approved, prove again including
those tests. If it requests changes, stop for another decision. Do not ship
an unapproved review.

## External facts checked

None. No dependency, external provider, version, price, quota or terms are
selected by this repair. Use the existing checked lock and accepted tool-version
exception. Confirm available existing reviewer allowance before launch; no
new spend or keys are authorized.

## Risks and mitigations

Static binding checks may reject unusual dynamic tests conservatively. Prefer
a clear error to false acceptance coverage; do not execute modules to decide.
Preserve scope boundaries and allowed cases so local variables cannot erase
unrelated test evidence. Keep all coverage, lint, typing, security and proof
gates. The old review failure remains recorded; the proposed extra round is
explicit and bounded. No private data, credentials or captured content is
needed.

## Size

Estimate 20–30 added non-test lines in the checker, plus tests and process
documentation. The original counting basis currently has 768 added lines;
the estimated combined 788–798 remains within the accepted 800-line cap.
Stop for a new decision if a readable fix exceeds that bound. Do not reduce
checks or compress code to fit.

## Rollback

Leave main unchanged. Retain the pushed branch, every native review in Git
history and every reviewer test. If the proposal is rejected, keep the
bootstrap unfinished. No database volume or user data is deleted.

## Log

Plan written 2026-10-26.

Proposal only, prepared after round 3 returned REQUEST_CHANGES. The remaining
blocker is supported by two reproduced failing tests. No new test, source,
backlog, branch-rule, review-budget or generated-artifact change is made by
this planning step. Await the user's approval before proceeding.
