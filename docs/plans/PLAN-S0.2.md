# PLAN S0.2 — Proof kit

## Goal

Give Lantern one repeatable way to check its code and save an honest report of the results. The report will say which exact committed code was checked, what ran, what passed or failed, and whether every job requirement has a test. This creates the proof tool needed to verify the first two foundation jobs together.

## Scope

In: extend the existing checks with import boundaries, coverage, prohibited-dependency checks, security lint and live public vulnerability lookups; trace backlog acceptance IDs to tests; compute a committed code-tree hash; generate proof reports through the sanctioned writer; unit/property/CLI tests; the small configuration and Makefile changes needed to expose those tools.

Out: investigation features, model calls, HTTP adapters, database schema changes, CI, safety hooks, automated review, deployment and GitHub account settings. Do not modify .codex/, .agents/, .github/, scripts/hooks/, scripts/review.py or scripts/review_schema.json. Do not record cassettes or author proof/review files manually. Do not lower coverage or security thresholds.

Use the existing story/M0-boot branch under docs/08 §5. S0.1's implementation/check step has been reported: make check passed all 115 tests in both the working Codespace and a clean checkout. S0.1 is not marked DONE or merged. The first two stories receive joint proof and independent review after this implementation, using PLAN-M0 and make prove STORY=M0 AC_STORIES="S0.1 S0.2". That later plan/proof/review is not executed during this planning step.

The user approved preparing this plan on 2026-10-23 and subsequently approved the plan before the tests-first step. ADR 0002 is current: no mandatory package-age wait, but current advisory checks, official sources and locked hashes remain required.

## Design

All new modules are development tools under scripts/, outside Lantern's runtime layers. They must not add imports to core, policy, the CLI or database implementation. Use standard-library argparse, ast, hashlib, subprocess, pathlib, tomllib and UTC clocks, plus the existing Pydantic dependency at file/process boundaries. No generic plugin framework or new runtime service.

Files to create or change:

| File | Purpose |
|---|---|
| scripts/__init__.py | Make development helpers importable for tests |
| scripts/checks.py | One ordered catalogue of check commands and a bounded runner |
| scripts/coverage_gate.py | Validate coverage JSON and apply configured thresholds |
| scripts/check_acceptance_ids.py | Read backlog IDs and inspect test ASTs without importing tests |
| scripts/check_dependencies.py | Scan the complete lockfile for prohibited packages |
| scripts/audit_dependencies.py, tests/test_audit_dependencies.py | Strict audit of the validated installed inventory under accepted ADR 0003 |
| scripts/code_tree.py | Hash committed Git tree entries with explicit prefix exclusions |
| scripts/prove.py | Run all checks, trace IDs, and write the generated proof artifact |
| Makefile | check/prove entry points; existing db/db-down/hooks behavior retained |
| pyproject.toml, uv.lock | Development dependencies, import contract, quality configuration and coverage settings |
| .gitignore | Add generated parallel coverage files/import-linter caches if needed |
| tests/test_check_pipeline.py, tests/test_coverage_gate.py, tests/test_acceptance_ids.py, tests/test_dependencies.py, tests/test_code_tree.py, tests/test_prove.py | Acceptance, property and process-boundary tests |
| tests/test_skeleton.py | Extend its existing five-check/fail-fast contract for the now-required ten checks |
| docs/plans/PLAN-S0.2.md | RED run and step evidence |

Keep the tools usable both from their documented script paths and as imported modules. A minimal, explained standalone-script import bootstrap is permitted where needed; do not package development tools into Lantern's application wheel or weaken lint rules to conceal import errors.

Public interfaces to implement after approval:

```python
# scripts/checks.py
class StepResult(BaseModel):
    command: tuple[str, ...]
    exit_code: int
    duration_seconds: float  # finite, non-negative
    output_tail: tuple[str, ...]  # at most 30 lines, sanitized

CHECKS: tuple[tuple[str, ...], ...]
StepRunner = Callable[[Sequence[str], Path], StepResult]

def run_step(command: Sequence[str], root: Path) -> StepResult: ...
def run_checks(root: Path, *, runner: StepRunner = run_step,
               continue_on_error: bool = False) -> list[StepResult]: ...
def main(argv: Sequence[str] | None = None) -> int: ...

# scripts/coverage_gate.py — ignore producer fields not used by the gate
class Summary(BaseModel):
    covered_lines: int
    num_statements: int
    covered_branches: int
    num_branches: int
    percent_covered: float

class CoveredFile(BaseModel):
    summary: Summary

class CoverageReport(BaseModel):
    totals: Summary
    files: dict[str, CoveredFile]

class QualitySettings(BaseModel):
    coverage_total: float
    coverage_critical: float
    critical_paths: tuple[str, ...]

def evaluate_coverage(report: CoverageReport, quality: QualitySettings,
                      present_paths: frozenset[str]) -> list[str]: ...
def main(argv: Sequence[str] | None = None) -> int: ...

# scripts/check_acceptance_ids.py
# selected IDs retain backlog order; test names include their source path.
def acceptance_ids(backlog_text: str, stories: Sequence[str]) -> list[str]: ...
def test_marks(source: str, path: str) -> dict[str, list[str]]: ...
def main(argv: Sequence[str] | None = None) -> int: ...

# scripts/check_dependencies.py
DENIED: frozenset[str]
def denied_packages(names: Sequence[str]) -> list[str]: ...
def main(argv: Sequence[str] | None = None) -> int: ...

# scripts/code_tree.py
# Entry streams are exact, ordered git ls-tree line bytes paired with raw paths.
def hash_entries(entries: Sequence[tuple[str, bytes]],
                 excluded_prefixes: Sequence[str] = ()) -> str: ...
def code_tree(root: Path, *, commit: str | None = None,
              excluded_prefixes: Sequence[str] = ()) -> str: ...
def main(argv: Sequence[str] | None = None) -> int: ...

# scripts/prove.py — input IDs use a restricted, filename-safe syntax
class ProofContext(BaseModel):
    story: str
    commit_sha: str
    code_tree: str
    recorded_at: AwareDatetime
    platform: str

def render_proof(context: ProofContext, results: Sequence[StepResult]) -> str: ...
def prove(story: str, ac_stories: Sequence[str], root: Path, *,
          runner: StepRunner = run_step) -> int: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

Validate JSON/TOML and subprocess-result structures before using them. Coverage counts must be non-negative, covered counts cannot exceed totals, percentages/thresholds must be finite and in range, and invalid or missing reports must fail clearly. Do not accept a partially parsed file. argparse/Pydantic error output must not dump real environment values.

The shared CHECKS catalogue runs these ten checks, in this order:

1. uv run ruff check .
2. uv run ruff format --check src scripts tests
3. uv run python scripts/lint_custom.py
4. uv run lint-imports
5. uv run mypy --strict
6. uv run --offline pytest with --cov, terminal coverage and --cov-report=json:coverage.json
7. uv run python scripts/coverage_gate.py
8. uv run python scripts/check_dependencies.py
9. uv run bandit -r src/lantern scripts
10. uv run python scripts/audit_dependencies.py (accepted ADR 0003; invokes pip-audit with --strict --no-deps --disable-pip --progress-spinner off --timeout 30 -r <temporary exact pins>)

Use pip-audit's documented --strict collection option so collection failure cannot be treated as success, and retain nonzero network/audit errors. Confirm the pinned CLI arguments during implementation. Do not use --fix, vulnerability ignore lists, --exit-zero or blanket source exclusions. Only Lantern's editable first-party package is excluded from public-package lookup; third-party dependencies remain audited. Bandit scans application and tool code; any genuine false-positive suppression must be narrowly scoped with a reason and logged, not a global lowering of the bar.

Make check invokes the shared runner in fail-fast mode. The proof command uses that same catalogue but continues after failed checks, then runs the acceptance-ID checker for all requested AC stories. No duplicated, drifting list of ten commands. The runner records nonzero outcomes for spawn/timeout failures, uses argument lists without a shell, imposes bounded subprocess waits and sanitizes sensitive environment values from captured output. A failure must never turn into a successful StepResult.

Explicitly update tests/test_skeleton.py's existing pipeline test under this approved plan: expand the expected five commands to all ten, preserve its per-step failure-injection cases, and let its fake uv hand off only the shared-runner bootstrap to the actual test interpreter. It must still exercise the real Makefile/runner and observe each external check in order. Do not delete or relax the fail-fast assertion; this is the planned S0.2 extension stated by S0.1-AC1.

Import contracts follow docs/02 §5 for modules currently present. Initially enforce lantern.cli above lantern.db; shared config remains outside that contract. Test a temporary illegal reverse import to demonstrate the contract can fail. Do not invent empty packages for future layers or configure non-existent core/policy/adapters as though they already exist. Their stories add the corresponding contracts when those modules are created. No circular or lateral runtime dependency is introduced by the tools.

Set tool.lantern.quality coverage_total=85 and coverage_critical=95. Copy these critical_paths exactly from docs/05 §5.1:

- src/lantern/core
- src/lantern/policy
- src/lantern/egress
- src/lantern/db/events.py
- src/lantern/tools/gateway.py
- src/lantern/llm/gateway.py
- src/lantern/report/render_html.py
- scripts/hooks

Coverage remains branch coverage of src/lantern and scripts. Add subprocess measurement support documented by coverage.py/pytest-cov if needed to measure real script executions; ignore only generated coverage/cache artifacts. Use unrounded percentages. Aggregate a critical directory by summing its covered/total line-and-branch opportunities, not averaging file percentages. Paths are matched on whole path-component boundaries. A configured path absent on disk is reported as "not present"; an existing required path missing from the report fails. A threshold equality passes. A gate cannot pass because input is malformed, empty or a previous run's report was reused.

Acceptance tracing reads headings and AC bullet lines from the backlog, then reads Python ASTs under tests/ without executing modules. Map explicit pytest.mark.ac literal strings to test names and source paths. Inspect every test module for unknown IDs, even outside the requested stories. Unknown stories, missing coverage, malformed/non-literal marker arguments and syntax errors produce nonzero results with clear messages. Strings containing example decorators are data, not markers. New synthetic JSON/TOML/Python inputs belong in temporary test directories, not tests/fixtures/.

The dependency deny-list normalizes case and runs of hyphens/underscores/dots using standard Python project-name rules. Scan every package in uv.lock, including transitives. Initial prohibited names: face-recognition, face-recognition-models, deepface, insightface, facenet-pytorch and dlib; also include litellm under the user's explicit supply-chain rule. General image libraries used by the design, such as Pillow, numpy and opencv-python, are not matched by broad substrings. Malformed/missing lockfiles fail; no prohibited package is installed to test this tool.

The code-tree digest is SHA256 over the exact ordered git ls-tree -r entries for one captured commit, excluding docs/ by default. Query raw NUL-separated path names separately if needed to safely identify quoted/unusual paths, while hashing the original Git line bytes; force stable Git path quoting. Prefix exclusions match complete path components, so docs-backup is retained when docs is excluded. Extra exclusions support tests/review for the later review tool. Do not hash working-tree caches or substitute the commit SHA for a tree-content hash.

Prove rejects tracked non-doc changes before running any check or writing an artifact. Include staged edits, deletions and both sides of renames; reject non-ignored untracked code too so unchecked source cannot influence the run. Docs-only changes are permitted. Capture HEAD once and use that immutable commit for the tree hash. Check again before declaring PASS if code/HEAD changed during the run. Remove only known generated, untracked coverage output before measurement so a stale report cannot pass; do not follow arbitrary paths or delete user data.

The writer alone produces docs/proofs/PROOF-<ID>.md. The report contains commit SHA, code-tree digest, UTC time, platform and for every command its exit code, duration, recognizable test/coverage/audit numbers and sanitized last 30 output lines. Preserve failed steps and later outcomes. Use output fencing that cannot be broken by command text containing backticks. End with RESULT: PASS only if every required step and provenance check succeeds; otherwise end RESULT: FAIL and exit nonzero. Write the artifact atomically. Unit tests call the sanctioned writer under temporary repositories; they do not hand-author PROOF or REVIEW files.

Make prove supports STORY and AC_STORIES from the backlog syntax. Pass those Make variables through the process environment and validate them as IDs; do not interpolate them into shell command text. The Python CLI still accepts the documented positional ID and --ac-stories arguments. Normal scripts return 0/1 for pass/fail and a clear nonzero usage/refusal status for invalid input.

## Acceptance criteria

- S0.2-AC1 `make check` runs, in this order, stopping at the first failure: `ruff check`, `ruff format --check`, `scripts/lint_custom.py`, `lint-imports` (layer contracts of 02 §5, covering only packages that exist), `mypy --strict`, the offline `pytest` suite with coverage, `scripts/coverage_gate.py`, `scripts/check_dependencies.py`, `bandit`, `pip-audit`. It exits 0 only when every step passes.
- S0.2-AC2 `scripts/coverage_gate.py` reads the coverage JSON report and fails when total coverage is below `coverage_total` or any existing path in `critical_paths` is below `coverage_critical` (all three read from `[tool.lantern.quality]` in `pyproject.toml`); configured paths that do not exist yet are listed as "not present", not failed.
- S0.2-AC3 `scripts/check_acceptance_ids.py <ID> [<ID> …] --backlog <path>` collects the AC IDs listed under each given story's heading in the backlog file, scans `tests/` for `@pytest.mark.ac(...)` without importing test modules, prints an AC → tests table, and fails when one of those ACs has no test or any test anywhere references an AC ID that appears nowhere in the backlog.
- S0.2-AC4 `scripts/prove.py <ID> [--ac-stories <ID> …]` (and `make prove STORY=<ID> [AC_STORIES="…"]`) refuses to run while tracked files outside `docs/` have uncommitted changes; otherwise it runs every `make check` step and `check_acceptance_ids.py` for the AC stories (default: `<ID>` itself), records all of them even after a failure, and writes `docs/proofs/PROOF-<ID>.md` with commit SHA, the code-tree hash (sha256 over the `git ls-tree -r HEAD` entries outside `docs/`, computed by `scripts/code_tree.py`, which accepts extra excluded prefixes), UTC time, platform, and for each step: command, exit code, duration, key numbers and the last 30 lines of output, ending in `RESULT: PASS` or `RESULT: FAIL`; it exits non-zero on FAIL. Tested with a stubbed step runner.
- S0.2-AC5 `[tool.lantern.quality]` sets `coverage_total = 85`, `coverage_critical = 95` and `critical_paths` = the paths listed in 05 §5.1; coverage measures `src/lantern` and `scripts`.
- S0.2-AC6 `scripts/check_dependencies.py` fails when `uv.lock` contains a package on its deny-list (face-recognition and face-embedding libraries, invariant 3 of 07 §1) and passes otherwise.

## Test plan

Each acceptance test has an explicit pytest.mark.ac decorator. Write tests and permitted signature stubs only after approval, run them RED for missing behavior, then log the real output before implementation. Existing S0.1 tests remain part of the suite; the explicit pipeline extension above is authorized by this plan's approval.

| AC | Files and tests | Kind / negative cases |
|---|---|---|
| AC1 | test_check_pipeline.py::test_required_order, ::test_stops_at_each_failure, ::test_spawn_and_timeout_fail, ::test_make_uses_shared_runner, ::test_import_contract_blocks_reverse_dependency; extended test_skeleton.py pipeline test | Unit, contract and CLI. Use fake external executables, not a mocked unit under test. Real make check validates the final integrated commands. |
| AC2 | test_coverage_gate.py::test_total_boundary, ::test_critical_boundary, ::test_weighted_directory_coverage, ::test_missing_path_is_reported, ::test_existing_unmeasured_path_fails, ::test_malformed_or_nonfinite_report_fails, ::test_no_prefix_collision, ::test_cli_status | Unit/property: increasing covered counts cannot cause a previous PASS to fail; aggregate bounds and file order do not change the result. Missing, empty and invalid JSON fail without a traceback exposing values. |
| AC3 | test_acceptance_ids.py::test_selected_story_ids, ::test_unknown_marker_anywhere_fails, ::test_missing_ac_fails, ::test_unknown_story_fails, ::test_literal_marker_required, ::test_never_imports_test_modules, ::test_cli_table, ::test_class_test_names | Unit/property/CLI. Synthetic backlog headings and temporary test modules, including an import-time side-effect trap. Properties: adding unrelated backlog stories does not change selected IDs, repeated story selection does not duplicate IDs, and reordering test files preserves mappings. Text in string literals is ignored. |
| AC4 | test_prove.py::test_dirty_code_refused, ::test_docs_only_changes_allowed, ::test_renamed_or_untracked_code_refused, ::test_all_steps_run_after_failure, ::test_defaults_and_combined_ac_stories, ::test_report_metadata_and_last_30_lines, ::test_head_or_code_change_fails, ::test_no_stale_coverage_pass, ::test_sensitive_values_redacted, ::test_story_path_traversal_rejected, ::test_make_variables_are_data; test_code_tree.py::test_git_entries_match_digest, ::test_docs_changes_do_not_change_hash, ::test_code_changes_change_hash, ::test_extra_exclusions_and_prefix_boundaries, ::test_unusual_paths | Fake step runner only where the AC explicitly requires it; actual temporary Git repositories and writer calls. Property-test hash prefix exclusions and safe rendering of arbitrary output/backticks; UTC/provenance and failure results are independent assertions. No real proof artifact is written in this step. |
| AC5 | test_check_pipeline.py::test_quality_configuration_and_sources, ::test_critical_paths_exact | Contract against the exact existing design thresholds, eight critical paths, and coverage measurement of src/lantern plus scripts. No nonexistent path is silently removed. |
| AC6 | test_dependencies.py::test_each_denied_name_fails, ::test_normalized_names, ::test_transitive_package_is_checked, ::test_allowed_image_packages, ::test_invalid_lock_fails, ::test_cli_status | Unit/property/CLI. Normalization is idempotent; equivalent case/separator spellings remain denied. Inputs are temporary synthetic TOML; no face-recognition package is installed. |

No research/API cassettes or eval worlds are needed: no investigation behavior changes. Offline pytest must not query package registries or models. The live pip-audit check is a separate explicit command in make check/prove; tests of the proof runner stub that external boundary and cannot claim the stubs are a real vulnerability audit.

New development requirements will be added with uv add --dev after explaining their purpose and rechecking current advisories. Resolve without sync first, check all selected transitive versions, official source URLs, hashes and yanked status, then sync the lockfile. Add only narrow, explained test-harness configuration and valid importable stubs needed for a legitimate RED run. Never import a nonexistent implementation at collection time or silently skip unavailable bootstrap tools.

## External facts checked

Checked 2026-10-23. No packages were installed and no project configuration/code changed during this planning step. PyPI version JSON and OSV queries for the exact candidates below returned no listed active advisories at lookup time; this is a point-in-time result, not a guarantee. Recheck before addition and audit the complete resolver result before sync under ADR 0002.

| Dependency | Candidate / PyPI metadata | Licence | Purpose |
|---|---|---|---|
| import-linter | [2.15](https://pypi.org/pypi/import-linter/2.15/json) | BSD 2-Clause License | Enforce current architecture import directions. |
| pytest-cov | [7.1.0](https://pypi.org/pypi/pytest-cov/7.1.0/json) | MIT | Run the existing offline pytest suite with coverage reporting. |
| coverage | [7.17.0](https://pypi.org/pypi/coverage/7.17.0/json) | Apache-2.0 | Produce/validate the JSON coverage format and support subprocess measurement; resolve/pin the producer alongside pytest-cov. |
| bandit | [1.9.4](https://pypi.org/pypi/bandit/1.9.4/json) | Apache-2.0 | Check application and development-tool ASTs for common security issues. |
| pip-audit | [2.10.1](https://pypi.org/pypi/pip-audit/2.10.1/json) | Apache-2.0 (PyPI classifier) | Check installed third-party versions against current public vulnerability records. |


The candidates' declared Python requirements include Python 3.12. They are development tools, not runtime investigation providers. No paid plan, API key, research quota or platform-content licence is required. No seven-day wait applies; the user's current security/advisory policy does.

Primary maintainer references:

- Import-linter layer contracts support modules/packages in high-to-low order and document missing-layer behavior: https://import-linter.readthedocs.io/en/latest/contract_types/layers/ . Configure only modules currently present.
- pytest-cov documents JSON/terminal reporting: https://pytest-cov.readthedocs.io/en/latest/reporting.html . Its 7.x subprocess behavior is documented at https://pytest-cov.readthedocs.io/en/latest/subprocess-support.html ; use the coverage.py mechanism rather than relying on removed automatic behavior.
- Coverage.py 7.17.0 was released 2026-10-22 and supports Python 3.12: https://coverage.readthedocs.io/en/7.17.0/ . Verify the actual producer JSON during implementation instead of inventing a schema: https://github.com/coveragepy/coveragepy/blob/7.17.0/coverage/jsonreport.py . The gate uses documented report counts and configured thresholds; extra producer fields are ignored only after required fields validate.
- Bandit processes Python ASTs for common security issues and uses Apache-2.0: https://bandit.readthedocs.io/en/latest/ . It complements dependency audits and tests; it does not replace them.
- pip-audit documents local environment audits, skip-editable, bounded network timeouts and nonzero vulnerability/error outcomes: https://github.com/pypa/pip-audit . It audits known vulnerabilities; it does not prove absence of malicious code. Never auto-fix the environment or waive findings in the proof command.
- Git documents ls-tree entry fields and NUL-separated output for unusual path handling: https://git-scm.com/docs/git-ls-tree . Use committed Git entries, never arbitrary working-directory bytes, for the report digest.

## Risks and mitigations

- Supply chain: candidates can change or receive advisories. Explain/recheck before adding, audit the full resolved graph before sync, use PyPI/official maintainer sources, commit hashes, retain current secure minimum constraints and never add litellm. The advisory lookup itself must fail closed on network/collection failure.
- Proof accuracy: fail-fast make check and all-steps prove share one catalogue. Clear only generated stale coverage output; refuse dirty/untracked code, capture a fixed commit, detect mutations during execution, and never fabricate PASS, test counts or proof contents. Metadata-only docs updates are the documented exception to the code-tree hash.
- Secrets and privacy: do not dump environment variables, Git author identity or credentials. Redact sensitive values from persisted command output, use only fixed report paths derived from validated IDs, escape arbitrary tool text, and do not include captured evidence or real personal data. Synthetic tests use fake data only.
- Process safety: fixed argument lists, cwd rooted at the repository, bounded timeouts and nonzero spawn/timeout results; no shell=True, command substitution, evaluator or arbitrary executable from a proof ID. Make variables are data through environment variables.
- Coverage meaning: never pass malformed/stale input, unmeasured existing critical paths or rounded below-threshold values. Keep the quality settings unchanged. Add real tests to reach the required coverage rather than exclusions, skips or lower thresholds.
- Size and scope: keep this a small developer kit. No generic workflow engine, plugin infrastructure, hooks, CI or reviewer launch. If the implementation needs more than the approved size, propose a split and seek approval before expanding it.
- Cost/terms: tests are offline; pip-audit makes explicit public package-name/version lookups. No investigation, paid service, model call or account setting changes. A network outage is a reported audit failure, not a reason to waive the check.
- Bootstrap carry-over: current Codespace and clean-checkout S0.1 checks passed, but a newly rebuilt Codespace was not verified. Keep that limitation visible when preparing joint M0 proof/review; do not claim this plan resolves it or mark either story DONE early. Review tooling is still delivered by S0.4; follow the documented manual bootstrap review later.

## Size

The original estimate was 350–400 handwritten non-test lines. Accepted ADR 0003 permits this one story up to 800, with an expected final size of approximately 700–750, after the implemented tools showed the original estimate was too small. Reuse existing dependencies and avoid a general-purpose framework. Tests, generated uv.lock/cache/coverage output and process documentation are counted separately. No quality gate or acceptance criterion changes. Stop for a new decision before exceeding 800.

## Rollback

Before merge, retain the pushed bootstrap branch and leave main unchanged. Remove/revert only S0.2 changes through a normal corrective commit/PR if needed; preserve the working S0.1 setup and its dependency-security fixes. Generated coverage and tool caches are disposable, not user evidence. Do not delete database volumes, real secrets, captured data or history. A proof/report failure is evidence to investigate, not a reason to edit the artifact or erase it. No external platform content or paid resource needs undoing.

## Log

Plan written 2026-10-23.

- The user approved preparing the next foundation job's plan after S0.1's green implementation/check report. This is pick/plan authorization only; tests/code approval remains pending.
- Read the plan skill, mandatory loop, proof/quality/test requirements, complete S0.2 ACs, docs/02 §5, docs/07 invariant 3 and docs/04 §10. Inspected the current Makefile, configuration and S0.1 pipeline test to identify the explicit test extension needed.
- Stayed on story/M0-boot under the documented bootstrap exception; the existing two-story branch is not recreated from main or merged.
- Queried exact candidate versions/licences/Python support and current PyPI/OSV advisories, and checked primary maintainer docs. Verified the five coverage JSON summary keys against the maintainer's tagged 7.17.0 jsonreport.py source, and verified pip-audit --strict in its documented CLI. No dependency installation, tests, stubs, implementation, proof or review occurred during this plan step.
- S0.1's pending fresh-container-rebuild limitation is carried forward without a fabricated result. No scope/AC changes are proposed; the six criteria in the Acceptance criteria section were copied verbatim from the backlog.

### RED run 2026-10-23

The user approved this plan. Used the tests-first skill on story/M0-boot. Added six test modules with explicit acceptance markers and Hypothesis properties for the planned pure functions. Extended the S0.1 pipeline contract exactly as approved: ten commands, failure injection at every step, and a narrowly matched fake-uv handoff to the actual Python interpreter for the shared-runner bootstrap.

Added only interface stubs: the approved model fields, empty command/deny-list constants and functions raising `NotImplementedError("S0.2: not implemented yet")`. The standalone proof stub has the minimal repository-root import bootstrap required to resolve its type/signature imports. No proof behavior, Makefile/configuration changes, dependency additions, fixtures, proof/review artifacts or investigation features were implemented.

Final RED command (stdout/stderr captured in /tmp/lantern-s02-red.log; JUnit detail in /tmp/lantern-s02-red.xml):

```sh
uv run --offline pytest tests/test_check_pipeline.py tests/test_coverage_gate.py tests/test_acceptance_ids.py tests/test_dependencies.py tests/test_code_tree.py tests/test_prove.py tests/test_skeleton.py::test_make_check_commands_and_failure_propagation -q --tb=line --junitxml=/tmp/lantern-s02-red.xml
```

Real result: exit 1; 169 cases collected, **165 failed, 4 passed, 0 errors, 0 skipped**, in 5.956 seconds. All failures were assertions or the deliberate stub's NotImplementedError, with no import, syntax, collection or fixture errors.

| Failure reason | Cases | Meaning |
|---|---:|---|
| NotImplementedError from the approved interface stubs | 131 | Coverage, requirement tracing, dependency denial, committed-tree hashing, process execution and proof generation have no implementation yet |
| AssertionError | 34 | Missing command catalogue, shared Make entry points, quality/import settings, CLI behavior and validation; the existing five-command pipeline does not yet satisfy its ten-command extension |

Four already-passing cases are legitimate regression guards: Pydantic's existing AwareDatetime type already rejects naive proof timestamps, and failure injection at the first three existing checks already stops the S0.1 Makefile. These retain working guarantees rather than claiming the new tools are implemented. All later pipeline cases and its success case are RED. The first exploratory run had 163 failures and 4 passes; the final run additionally covers rounded percentages and partially unmeasured critical directories.

The acceptance-ID checker is itself an unimplemented S0.2 stub, so the skill's bootstrap exception applies: no acceptance-tracing command is claimed to have run successfully. Every new test explicitly names one of the six backlog ACs. No cassette recorder is needed or used.

Test/stub housekeeping checks passed using the existing environment: ruff check, ruff format --check (30 files), custom lint, and strict mypy (15 source files). These are not a full make check, PROOF or independent review. The intentionally RED checkpoint will become green only after implementation; neither bootstrap story is marked DONE or merged.

### Implementation checkpoint and amendment proposal 2026-10-23

The user asked what comes next after the pushed RED checkpoint. Started the
approved implementation skill on story/M0-boot. The following is partial work,
not completion of the implementation step.

- Explained why all five planned development dependencies are needed. Rechecked
  exact PyPI metadata and OSV advisories, then ran uv add --dev --no-sync for
  import-linter 2.15, pytest-cov 7.1.0, coverage 7.17.0, bandit 1.9.4 and
  pip-audit 2.10.1. Before uv sync --frozen, checked all 75 registry packages in
  uv.lock: official PyPI sources, files.pythonhosted.org URLs, matching SHA256
  hashes, no yanked artifacts and no active PyPI/OSV advisories. Installed the
  checked lock. No package-age wait was imposed under ADR 0002.
- Built the shared ten-command runner, bounded/sanitized process results,
  coverage validation and thresholds, complete-lock dependency deny-list and
  committed Git-tree digest. Connected Make check/prove entry points; added
  the exact quality paths, current CLI/database import contract, subprocess
  coverage configuration and generated-cache ignores. No tests were changed.
- Targeted verification of these four implemented tools and their wiring:
  `uv run --offline pytest tests/test_dependencies.py tests/test_code_tree.py tests/test_coverage_gate.py tests/test_check_pipeline.py tests/test_skeleton.py::test_make_check_commands_and_failure_propagation -k 'not check_acceptance_ids.py and not prove.py' -q --tb=short --junitxml=/tmp/lantern-s02-built-tools.xml`.
  The two deselected parameter cases are the standalone help checks for the
  two unimplemented scripts, not skips or a changed suite. Full tests remain
  required. A preceding run without that selection passed 112 cases and failed
  exactly those two cases. No full make check/PASS is claimed.
  The final targeted rerun after Git executable-path hardening exited 0:
  **112 passed, 0 failed, 0 errors, 0 skipped**, in 9.423 seconds.
- Ruff, format, custom lint and strict mypy passed. Bandit initially reported
  five low-severity process-launch warnings. Resolved Git to its installed
  absolute executable; narrowly documented B404 and B603 suppressions only at
  the required subprocess imports and argument-list calls. No shell execution,
  global scanner exclusions or security threshold changes. Bandit then exited
  0 without findings or warnings.
- The literal approved audit command failed, exit 1:
  `ERROR:pip_audit._cli:lantern: distribution marked as editable`.
  Inspection of the installed official 2.10.1 source confirmed that --strict
  treats even --skip-editable's intended exclusion as a fatal collection skip.
  The exact catalogue test therefore demands an invalid command. It has not
  been edited or weakened, and --strict has not been removed.
- Verified a proposed replacement read-only: generated exact pins for all 74
  installed third-party packages, verified that the only omitted editable is
  local Lantern, and ran pip-audit --strict --no-deps --disable-pip
  --progress-spinner off --timeout 30 -r /tmp/lantern-s02-installed-requirements.txt.
  Exit 0: No known vulnerabilities found. This is diagnostic evidence only,
  not the future helper, the full gate or a proof artifact.
- Measured 397 added handwritten non-test lines, including remaining stubs and
  configuration, relative to S0.1 implementation commit 0464260. Tracing and
  proof generation remain stubs. Stop here before expanding the approved size
  or changing the incorrect test. Proposed ADR 0003 documents both the split
  alternative and the recommended one-story exception (up to 800 lines), plus
  the exact audit-helper/test correction. User approval is pending. No new
  helper, changed test, accepted policy exception, proof, review or merge has
  been produced. S0.1's fresh-container rebuild limitation remains open.

Proposed amendment for approval:
[ADR 0003 — Proof kit size exception and strict package auditing](../adr/ADR-0003-proof-kit-size-and-strict-audit.md).

### Amendment accepted 2026-10-23

The user approved ADR 0003. Recorded its narrow 800-line exception in AGENTS.md
and docs/05 before further code. Correct only the invalid audit catalogue entry,
the matching fake-uv label and standalone-script coverage; retain every other
assertion and all six acceptance criteria. Add tests and a RED checkpoint for
the audit helper before implementing it. The helper's interfaces are
`installed_requirements(root: Path) -> list[str]`,
`audit(root: Path, *, runner: StepRunner = run_step) -> int`, and
`main(argv: Sequence[str] | None = None) -> int`. Property-test sorted,
order-independent exact pins, plus the inventory/strict-audit cases in ADR 0003.
The earlier pending proposal and failure evidence remain historical log entries.

### Additional RED run 2026-10-23 — accepted audit correction

Changed only the approved audit expectation, matching fake-uv label and CLI
parameter list. Added 16 audit-helper cases and signature-only stubs. No helper
behavior was implemented before this run.

Command: `uv run --offline pytest tests/test_audit_dependencies.py tests/test_check_pipeline.py::test_required_order tests/test_check_pipeline.py::test_standalone_scripts_have_working_cli tests/test_skeleton.py::test_make_check_commands_and_failure_propagation -q --tb=line --junitxml=/tmp/lantern-s02-audit-red.xml`.

Real exit 1 in 8.112 seconds: **22 failed, 13 passed, 0 errors, 0 skipped**.
16 failures are the audit stubs' NotImplementedError; six are assertions for
the changed catalogue, missing CLI behavior and final pipeline step. The 13
passing cases are regression guards: four built scripts already support help,
and injection at the first nine existing commands already stops correctly.
No import, syntax, collection or fixture error occurred. Captured output is
/tmp/lantern-s02-audit-red.log. Ruff and strict mypy passed on this checkpoint.
The requirement tracer remains a stub, so no acceptance-check success is claimed.

### Implementation and advisory test audit 2026-10-23

Implemented the accepted design and ADR 0003 without further dependencies.

- The strict audit helper validates the complete installed distribution inventory,
  rejects malformed/duplicate metadata and unexpected editable packages, omits
  only verified local Lantern, and runs pip-audit on temporary exact pins with
  strict collection and no installation/resolution. Temporary files are removed
  on success and failure. Package validation is shared with the lock deny-list.
- The requirement tracer reads backlog headings/AC lines and Python ASTs, maps
  explicit literal markers to test paths/names, never imports test modules, and
  fails missing/unknown requirements or malformed source/markers. It does not
  count nested functions or methods of non-test classes as collected tests.
- The proof writer validates filename-safe IDs, rejects dirty/untracked code
  including both sides of renames, captures one committed SHA/tree digest, clears
  only generated untracked coverage files, runs all ten checks plus AC tracing,
  and checks provenance again before PASS. It records bounded/redacted output,
  UTC, platform, commands, exits and durations with safe Markdown fences, writes
  atomically, and refuses symlinked proof directories. No repository proof or
  review artifact was generated at this implementation step; writer tests use
  isolated synthetic Git repositories.
- Advisory test-audit skill completed read-only over the PLAN, tests and tools.
  No unit under test was mocked, no vacuous acceptance test was found, and every
  planned pure function has a Hypothesis property. Inventory, subprocess and
  audit stubs represent external boundaries; real Make, Git and writer tests
  verify the actual behavior. No research/API cassette is applicable.
- The audit found missing cases in tests/test_acceptance_ids.py/test_marks:
  bare markers, nested functions and non-test classes; and in
  tests/test_check_pipeline.py/run_checks: exceptions or invalid results from
  the runner boundary must be recorded while later checks still run. Added six
  cases in tests/test_proof_boundaries.py. Their pre-fix command was
  `uv run --offline pytest tests/test_proof_boundaries.py -q --tb=line --junitxml=/tmp/lantern-s02-boundaries-red.xml`:
  **6 assertion failures, 0 errors, 0 skipped**, exit 1 in 0.205 seconds.
  Fixed those cases using a shared validating invocation wrapper, which also
  handles the proof writer's final AC check. No existing assertion was weakened.
- Initial full make check reached pytest and reported 294 passed/1 failed:
  a nested Make invocation added entering/leaving-directory text to the dry-run
  command assertion. Added MAKEFLAGS += --no-print-directory; the assertion stays
  exact and unchanged. The subsequent targeted run of proof/audit/tracing and
  boundary cases passed all 77 cases in 5.756 seconds.
- Final `make check` exited **0**. All ten ordered checks passed: ruff, format,
  custom lint, current CLI/database import contract, strict mypy (16 files),
  **301 tests in 52.73 seconds**, coverage gate, dependency deny-list, Bandit,
  and the live strict advisory audit. Total line-and-branch coverage was
  **95.90723055934515%**. All eight future critical paths were explicitly listed
  as not present. Coverage/security thresholds remain unchanged. Bandit found
  no issues and pip-audit reported no known vulnerabilities. Its advisory
  warning about hashless lookup input is retained: installation authority
  remains the previously checked, version/hash-locked uv.lock; the helper only
  queries already installed exact versions and disables installation/resolution.
  Full output is /tmp/lantern-s02-make-check.log; coverage.json is generated and
  ignored. AC tracing for S0.1 and S0.2 also exited 0 with all 13 criteria mapped
  and no unknown markers.
- Final measured handwritten non-test additions: **694 lines** relative to
  S0.1 implementation commit 0464260, counting .gitignore, Makefile,
  pyproject.toml and scripts/, excluding generated uv.lock, tests and process
  documentation as agreed. This is within ADR 0003's 800-line cap.
- No runtime investigation code, schema, harness, CI, fixtures, paid service,
  GitHub account setting or other repository changed. Main is unchanged. The
  implementation step is green, but neither bootstrap story is marked DONE:
  joint PLAN-M0, formal generated proof and fresh independent review remain.
  The unverified fresh-container-rebuild limitation from S0.1 remains explicit.
