# PLAN M0 — Prove and independently review the first two foundation jobs

## Goal

Verify the repository setup and proof kit together, save machine-generated evidence of the exact committed code, and have a fresh independent reviewer try to find defects before either job can be shipped. This is the one-time S0.1/S0.2 bootstrap of docs/08 §5, not the whole M0 milestone.

## Scope

In: joint proof of all S0.1 and S0.2 acceptance criteria, investigation of the outstanding fresh-container verification gap, the documented pre-S0.4 manual independent review, retained adversarial tests, fixes required by real review blockers, and repeat proof/review as needed (maximum three review rounds). Reuse story/M0-boot and the approved story plans and accepted ADRs.

Approved amendment (2026-10-26): ADR 0005 adds the narrow devcontainer setup
correction, its associated tests, and the explicit S0.1-AC6 preservation-clause
change. The original logs below remain historical. No other harness or CI
change is included.

Out: S0.3 and later stories, new product features, new runtime dependencies, schema migrations, CI/harness changes, paid services, account settings, opening/merging a PR, deployment and declaring the whole M0 milestone complete. Shipping is a later step and merging still requires a separate yes. No new proof/review runner is built.

The S0.2 implementation is committed and pushed at 20a20a4. Its full make check exited 0: 301 tests, 95.90723055934515% coverage, all ten ordered checks green. No formal PROOF or independent REVIEW exists yet. S0.1's current-Codespace and clean-checkout results do not prove a newly rebuilt container; that gap must remain visible and cannot be waived as part of this plan.

## Design

No new application module, function interface, layer, migration or generic framework is proposed. Use the already approved interfaces in PLAN-S0.1 and PLAN-S0.2; their original RED evidence remains authoritative. This joint plan does not repeat tests-first/implementation for working code or replace either story's acceptance criteria.

ADR 0005 setup interface: `.devcontainer/setup.sh [INSTALL_ROOT]` is a Bash
installer for Linux x86_64. Its default root is
`$HOME/.local/share/lantern-tools`; an explicit root permits isolated tests.
It downloads only pinned official Node, uv and Codex archives with committed
SHA256 digests. Constants are `NODE_VERSION`, `UV_VERSION`, `CODEX_VERSION`
and their corresponding `<TOOL>_SHA256` values. Authenticate all three
downloads before extracting or installing anything. Network failure, digest
mismatch or an unsupported platform exits nonzero. Successful installation
makes `node`, `npm`, `npx`, `uv`, `uvx` and `codex` available under
`INSTALL_ROOT/bin`. Configure the devcontainer to select that directory before
inherited tool paths. Pin a maintained Microsoft universal image by digest;
retain its Docker and GitHub CLI support. Tool versions require the applicable
advisory checks or the explicit existing-version exception accepted in ADR
0006; no unsafe pin is approved merely because it is the newest release.
Project Python remains 3.12 through
the existing pin and uv's managed-interpreter checksum verification.

New tests in `tests/test_devcontainer_setup.py` cover the image pin, setup
registration/PATH, all three per-tool checksum failures, an HTTP failure,
unsupported architecture, successful installation using harmless local
archives, and failure of the final download without partial installation.
They run offline: subprocess download commands are replaced with local test
programs, and test archives are authored only under pytest's temporary
directory. No cassette or captured source is involved. The existing pack
preservation test changes only for the approved devcontainer exception.

Files expected to change: this plan's Log, generated docs/proofs/PROOF-M0.md, the sanctioned reviewer CLI's docs/reviews/REVIEW-M0.json, and only fresh reviewer tests under tests/review/test_m0_r<round>_adversarial.py. Real blockers may require fixes confined to the two approved story scopes, followed by new proof/review; ask before correcting a wrong existing test, exceeding S0.2's accepted 800-line cap, expanding scope, or touching any protected harness/CI file. Do not hand-write or edit artifacts.

Execution after approval:

1. Verify clean committed code and the 13-criterion trace. Resolve the fresh-container evidence gap through the approved ADR 0005 setup correction and isolated fresh-container verification where safely possible. Do not rebuild/stop the active Codespace, create billable resources, install unreviewed tools or execute an unchecked mutable installer. If a user-assisted rebuild or a further scope change is necessary, present the concrete action and seek approval; do not mark S0.1-AC6 satisfied without real evidence. The current image is not cached and no devcontainer CLI is installed, so success is not assumed.
2. Run exactly make prove STORY=M0 AC_STORIES="S0.1 S0.2" on committed code. Read the generated report and verify commit SHA, code-tree digest, UTC/platform, all 11 results, counts/coverage, and final RESULT. Report a failure honestly, fix its cause within scope, commit and repeat. Commit/push the generated proof before review.
3. Apply the review skill's manual bootstrap exception (docs/05 §4.1–§4.2), showing each command first. Create an owned throwaway worktree at the reviewed HEAD and sync the checked lock. Keep the original prompt and shipped schema unchanged. Substitute STORY=M0, STORY_SLUG=m0, ROUND=1 (then 2/3), BASE=main in memory. Start a fresh ephemeral Codex reviewer using the documented different model, workspace-write sandbox and approval_policy="never"; never bypass the sandbox. Check model availability and existing quota before launch; ask before any new charge.
4. Resolve the existing review-metadata documentation inconsistency through proposed ADR 0004 as part of this plan's approval. Use a temporary schema extending the unchanged shipped schema with the exact precomputed code_tree enum; codex exec --output-last-message remains the sole review writer. Validate the review payload against the original schema separately from the fixed digest/HEAD metadata. Do not edit the prompt, schema, scripts/review.py or any generated review. Add only the accepted explanatory docs/05 note before using this procedure.
5. Verify the reviewer evaluated all 13 ACs, created and ran at least six adversarial tests, and reported its actual verdict and blockers. Validate its HEAD and digest, copy back only its new test file, list/discard other worktree changes, and remove only the owned worktree. A database connection blocked solely by the review sandbox is a note per the prompt, never a fabricated test pass. Commit/push the reviewer tests and generated review.
6. Fix supported REQUEST_CHANGES findings, then prove and obtain another fresh review. Keep earlier reviewer tests permanently. After APPROVE, prove again on the commit including reviewer tests. Stop after three unsuccessful rounds and propose a split. Do not mark either story DONE until all required evidence and the later merge exist.

## Acceptance criteria

Copied verbatim from the backlog, as required by docs/08 §5. The user approved
only the S0.1-AC6 preservation-clause change in ADR 0005; it is reflected in
the backlog and both plans. All other criterion text remains unchanged.

- S0.1-AC1 `uv sync` on a fresh clone succeeds (Python 3.12 pinned in `.python-version`, `uv.lock` committed); `make check` runs `ruff check`, `ruff format --check`, `scripts/lint_custom.py`, `mypy --strict` and the offline `pytest` suite, and is green with one placeholder test; `make db` and `make db-down` start and stop the compose database. (S0.2 extends `make check`.)
- S0.1-AC2 `pyproject.toml` (uv project `lantern`, src layout, console script `lantern`) carries the tool configuration of 05 §2.1; a test asserts each key.
- S0.1-AC3 `docker compose up db` starts Postgres 16 with pgvector (current `pgvector/pgvector` pg16 tag, verified in the PLAN) with a healthcheck, bound to `127.0.0.1:${LANTERN_DB_PORT:-5434}`; `config.Settings` reads `LANTERN_DATABASE_URL` as a secret and accepts only the `postgresql+asyncpg` driver; `lantern db upgrade` applies an empty baseline Alembic migration. The e2e test uses the compose database and fails with a pointer to `make db` when it is down.
- S0.1-AC4 `.pre-commit-config.yaml` uses only local hooks run through `uv run`: end-of-file and trailing-whitespace fixers, ruff, ruff format, mypy, detect-secrets with a committed baseline; `make hooks` installs them.
- S0.1-AC5 `scripts/lint_custom.py` reports each forbidden pattern of 05 §2.1 (one test per pattern, with allowed variants) and passes clean code; property test: it never raises on valid Python.
- S0.1-AC6 The shipped review schema, `.codex/` and `.agents/` are kept unchanged; `.devcontainer/` may receive the setup correction approved in ADR 0005; the dev container still builds a working Codespace after S0.1: Python 3.12, uv, Docker inside the container, Node LTS, the GitHub CLI and the Codex CLI; `make check` passes inside it. `.gitignore` covers `.env`, `.venv/`, `var/` and tool caches; `.env.example` lists every setting with placeholders; a test asserts no `.env` file is tracked.
- S0.1-AC7 `README.md` explains what Lantern is in plain words and how to open it in a Codespace, without secrets or personal data.
- S0.2-AC1 `make check` runs, in this order, stopping at the first failure: `ruff check`, `ruff format --check`, `scripts/lint_custom.py`, `lint-imports` (layer contracts of 02 §5, covering only packages that exist), `mypy --strict`, the offline `pytest` suite with coverage, `scripts/coverage_gate.py`, `scripts/check_dependencies.py`, `bandit`, `pip-audit`. It exits 0 only when every step passes.
- S0.2-AC2 `scripts/coverage_gate.py` reads the coverage JSON report and fails when total coverage is below `coverage_total` or any existing path in `critical_paths` is below `coverage_critical` (all three read from `[tool.lantern.quality]` in `pyproject.toml`); configured paths that do not exist yet are listed as "not present", not failed.
- S0.2-AC3 `scripts/check_acceptance_ids.py <ID> [<ID> …] --backlog <path>` collects the AC IDs listed under each given story's heading in the backlog file, scans `tests/` for `@pytest.mark.ac(...)` without importing test modules, prints an AC → tests table, and fails when one of those ACs has no test or any test anywhere references an AC ID that appears nowhere in the backlog.
- S0.2-AC4 `scripts/prove.py <ID> [--ac-stories <ID> …]` (and `make prove STORY=<ID> [AC_STORIES="…"]`) refuses to run while tracked files outside `docs/` have uncommitted changes; otherwise it runs every `make check` step and `check_acceptance_ids.py` for the AC stories (default: `<ID>` itself), records all of them even after a failure, and writes `docs/proofs/PROOF-<ID>.md` with commit SHA, the code-tree hash (sha256 over the `git ls-tree -r HEAD` entries outside `docs/`, computed by `scripts/code_tree.py`, which accepts extra excluded prefixes), UTC time, platform, and for each step: command, exit code, duration, key numbers and the last 30 lines of output, ending in `RESULT: PASS` or `RESULT: FAIL`; it exits non-zero on FAIL. Tested with a stubbed step runner.
- S0.2-AC5 `[tool.lantern.quality]` sets `coverage_total = 85`, `coverage_critical = 95` and `critical_paths` = the paths listed in 05 §5.1; coverage measures `src/lantern` and `scripts`.
- S0.2-AC6 `scripts/check_dependencies.py` fails when `uv.lock` contains a package on its deny-list (face-recognition and face-embedding libraries, invariant 3 of 07 §1) and passes otherwise.

## Test plan

Run the full existing offline suite and all subsequent review tests. Keep the original RED logs in both approved story plans; joint verification adds adversarial tests rather than relabeling previously passing tests as RED.

| Criterion | Existing tests and kind |
|---|---|
| S0.1-AC1 | tests/test_skeleton.py::test_make_check_commands_and_failure_propagation, ::test_python_pin_and_lockfile, ::test_db_targets; CLI and Make contracts; recorded clean-checkout sync plus actual db/check commands |
| S0.1-AC2 | tests/test_tooling.py::test_required_tooling_keys, ::test_src_package_and_console_entry, ::test_dependency_security_policy; configuration contracts |
| S0.1-AC3 | tests/test_config.py::test_database_url_valid_driver, ::test_secrets_hidden_in_errors_and_repr; tests/e2e/test_database.py::test_upgrade_records_baseline, ::test_upgrade_is_idempotent, ::test_missing_database_guidance; unit/property and database e2e |
| S0.1-AC4 | tests/test_hooks.py::test_all_hooks_are_local_uv_commands, ::test_make_hooks_installs, ::test_secret_scanner_detects_synthetic_token; actual local tools/contracts |
| S0.1-AC5 | tests/test_lint_custom.py::test_broad_handler_rules, ::test_shell_requires_literal_false, ::test_valid_python_never_raises, ::test_cli_exit_and_diagnostics; unit/property/CLI |
| S0.1-AC6 | tests/test_workspace.py::test_pack_files_unchanged, ::test_gitignore_protects_local_material, ::test_no_tracked_env, ::test_development_commands_available; contracts plus real fresh-container evidence, currently outstanding |
| S0.1-AC7 | tests/test_readme.py::test_readme_explains_product_and_codespaces, ::test_readme_has_setup_commands; documentation contracts |
| S0.2-AC1 | tests/test_check_pipeline.py::test_required_order, ::test_stops_at_each_failure, ::test_import_contract_blocks_reverse_dependency; tests/test_audit_dependencies.py::test_strict_arguments_status_and_manifest_cleanup, ::test_real_process_boundary_and_error_output; tests/test_proof_boundaries.py::test_runner_boundary_failure_is_recorded_and_later_steps_run; process/contract/property tests |
| S0.2-AC2 | tests/test_coverage_gate.py::test_total_boundary, ::test_critical_boundary, ::test_weighted_directory_coverage, ::test_no_prefix_collision, ::test_aggregation_bounds_and_order; unit/property/CLI |
| S0.2-AC3 | tests/test_acceptance_ids.py::test_never_imports_test_modules, ::test_literal_marker_required, ::test_unknown_marker_anywhere_fails; tests/test_proof_boundaries.py marker/collection cases; AST unit/property/CLI |
| S0.2-AC4 | tests/test_prove.py::test_dirty_code_refused, ::test_all_steps_run_after_failure, ::test_report_metadata_and_last_30_lines, ::test_head_or_code_change_fails, ::test_sensitive_values_redacted, ::test_render_arbitrary_backticks_and_failure; tests/test_code_tree.py digest properties and actual Git contracts; writer/process/property tests |
| S0.2-AC5 | tests/test_check_pipeline.py::test_quality_configuration_and_sources, ::test_critical_paths_exact; exact configuration contracts |
| S0.2-AC6 | tests/test_dependencies.py::test_each_denied_name_fails, ::test_transitive_package_is_checked, ::test_normalization_is_idempotent_and_case_equivalent; lockfile unit/property/CLI |

Reviewer focus: false PASS, dirty/renamed/untracked code, malformed markers and coverage, Unicode/unusual paths, subprocess failures, complete strict auditing, secret redaction, artifact/provenance integrity, setup reproducibility and test quality. Every new reviewer file is retained. No investigation/API cassettes or eval cases are applicable; the public vulnerability lookup remains a separate live gate, not an offline test claim.

## External facts checked

No new provider, price, rate limit, licence or dependency version is selected by this verification plan. Reuse the exact checked lock and accepted ADRs. The full strict audit passed on 2026-10-23 with no known vulnerabilities. Recheck advisories before any installation/update; no package-age delay applies under ADR 0002.

Read installed codex exec --help on 2026-10-23: --cd, --model, --sandbox workspace-write, --ephemeral, --output-schema, --output-last-message and -c are present. Reading help did not launch a reviewer, authenticate, modify account settings or change harness files. The documentation's reviewer model availability/quota is not assumed from the help output; verify before actual launch. No paid API or new account is authorized.

The fresh setup uses mcr.microsoft.com/devcontainers/universal:2 and a mutable postCreateCommand installing uv/Codex. Its exact current image/tools and supply-chain checks must be verified before any isolated rebuild. A newly rebuilt Codespace has not been claimed. No unchecked installer or extra tool install is authorized merely by this plan.

## Risks and mitigations

- Honest provenance: commit before proof; verify immutable code digest and reviewed HEAD; rerun after review tests/fixes. Machine PASS does not fill a missing fresh-container acceptance check or replace independent review.
- Artifact integrity: only the prove writer and reviewer CLI write their artifacts. Proposed ADR 0004 handles the shipped schema's missing metadata field without hand-editing outputs or the protected schema/prompt. Reject invalid output rather than repair it.
- Isolation/security: argument lists, owned throwaway paths, sandboxed reviewer, no platform write actions, no secret values in prompts/logs/artifacts, no captured evidence or personal data committed. Validate every copied-back path and discard unrelated reviewer changes.
- Scope/size: keep fixes within the approved bootstrap plans and accepted size exception. No skipped loop steps or lowered gates. Any real test correction, protected-file change or rescope needs approval.
- Setup and cost: do not interrupt the active Codespace, change account settings or create paid resources. If isolated verification cannot close AC6, report the remaining concrete action for approval. Use existing Codex access only; quota/model unavailability is a reported limitation, not permission to buy API access.
- CI/review tooling: S0.4/S0.5 are not built yet. Use only the documented manual bootstrap review exception; do not claim make review or CI ran. No merge is authorized by this plan.

## Size

The original verification plan proposed zero new runtime/non-test code. The
accepted ADR 0005 amendment permits up to 100 handwritten non-test setup lines.
The current S0.2 implementation is 694 handwritten non-test added lines; even
counting all proposed setup lines against that cap would total at most 794,
below its accepted 800-line limit. Reviewer tests and generated evidence are
counted separately. Necessary fixes must remain inside that cap or stop for a
new size decision; no speculative product feature or review harness is proposed.

## Rollback

Keep main unchanged and retain the pushed bootstrap branch. Delete only a verified, owned throwaway worktree after copying its allowed new tests. Preserve earlier reviewer tests and the actual generated evidence. If proof/review fails, leave the stories unfinished and fix the cause; never erase failures or alter verdicts. Do not delete database volumes, user data, other repositories or history.

## Log

Plan written 2026-10-23.

- S0.2 implementation completed, full make check passed and commit 20a20a4 was pushed before starting this joint planning step.
- Read the plan/prove/review skills, docs/05 workflow/plan/reviewer requirements, the unchanged review schema, both approved story plans and the bootstrap rule in docs/08. Read installed CLI help only.
- Copied all 13 AC lines directly from the backlog. No additional acceptance criterion or new feature is proposed. Prepared proposed ADR 0004 for the existing schema/metadata inconsistency; it is not accepted or used yet.
- The fresh-container evidence gap remains explicit. No new container, reviewer session, proof/review artifact, runtime code, dependency, harness/CI change or merge occurred during planning. User approval of this plan and its proposed manual metadata clarification is pending.

### Approved continuation and setup inspection — 2026-10-26

The user instructed "continue lantern from plan M0". Treated this as approval
of the saved plan, including its explicitly included ADR 0004 procedure.
Accepted that ADR and added the authorized docs/05 explanation. This log is
append-only; the original planning entry above records the earlier state.

Confirmed a clean `story/M0-boot` at ef81346, tracking its origin branch.
Read the starting notes, bootstrap workflow, prove/review skills and existing
story evidence. No proof or review artifact exists yet.

Execution step 1 used read-only local and official-registry inspection.
Docker is available; no devcontainer CLI is installed and the base image is
not cached. The configured universal:2 tag currently resolves to image version
2.13.1 from May 2025 (3.57 GiB compressed). Microsoft's matching inventory lists
Node 20.19.1/22.15.0. The unchanged postCreateCommand does not update Node.
The official release index identifies v24.22.1 as latest patched LTS today;
the running workspace has that version already. See proposed ADR 0005 for
exact digests, primary-source links and the narrow setup amendment.

The saved configuration therefore conflicts with the current Node security
policy, while S0.1-AC6 and its existing preservation test forbid editing it.
Prepared ADR 0005 as a proposal for the user, not an accepted rescope. It
specifies the affected configuration/test/criterion, RED-before-code sequence,
size bound and fresh-environment verification. Approval is required before
changing that requirement or configuration. Rebuilding alone does not fix the
saved setup. No image, installer, package or new tool was downloaded for
execution. No configuration, test, source, harness or CI file was changed;
the database and active Codespace were left untouched.

Stopped before the proof step, preserving the plan's execution order. No
`make prove`, independent review, successful fresh-container test or completed
bootstrap is claimed. Save/push this documentation checkpoint and ask for
approval of the concrete setup amendment before dependent work.

Checkpoint validation: `git diff --check` passed. The real pre-commit secret
scanner refreshed `.secrets.baseline`: the same two existing workflow findings
moved down one line, its timestamp changed, and it recorded its standard
baseline-file exclusion. Finding hashes/counts are unchanged. Retain that
tool-generated refresh; no baseline was hand-edited. No full quality-gate
result is claimed for this documentation checkpoint.

### RED run 2026-10-26 — approved fresh-setup amendment

The user replied "approve" to the explicit request to update workspace setup
and its matching requirement/tests. Accepted ADR 0005, changed only the
S0.1-AC6 preservation clause in its three authoritative copies, and adjusted
`test_pack_files_unchanged` only to exclude the authorized devcontainer path.
The original `.codex/`, `.agents/` and review schema still have byte-for-byte
checks. No original RED log or other acceptance criterion was changed.

Used the tests-first skill. Added eight tests under S0.1-AC6 for the corrected
setup, including all three digest failures, failed final download, unsupported
host and a positive installation path using harmless local test archives.
The installer interface is documented above. Tests author no files under
`tests/fixtures/`; no external binary is executed by the test harness.

Final RED command (using the existing environment without dependency syncing):

```sh
UV_CACHE_DIR=/tmp/lantern-uv-cache UV_NO_SYNC=1 uv run --offline pytest tests/test_devcontainer_setup.py -q --tb=line
```

Exit 1: **8 failed, 0 passed**, all AssertionErrors; no collection/import errors.

| Failure reason | Count |
|---|---:|
| Existing image lacks the maintained-image/digest pin | 1 |
| Existing post-create command lacks verified setup and selected tool PATH | 1 |
| Verified installer does not exist yet (positive path and five negative cases) | 6 |

The subsequent implementation must exercise the deeper assertions after those
missing setup assertions are satisfied; this RED run does not claim they have
executed yet. No signature stub is needed for this shell entry point: its
absence is an explicit behavioral/configuration assertion, not an import error.

The amended existing regression guards were run separately:

```sh
UV_CACHE_DIR=/tmp/lantern-uv-cache UV_NO_SYNC=1 uv run --offline pytest tests/test_workspace.py -q --tb=line
```

Exit 0: **13 passed**. These legitimate regression guards predate the amendment;
their passing result is not relabeled as new RED evidence. Ruff check and
formatting passed on both touched test files. The real command
`uv run --offline python scripts/check_acceptance_ids.py S0.1 S0.2 --backlog
docs/06_ROADMAP_BACKLOG.md` (same cache/no-sync environment) exited 0; every one
of the 13 ACs has tests and no unknown ID was reported. `git diff --check` passed.

### Supply-chain checks and implementation blocker — 2026-10-26

Read official OpenAI CLI installation guidance, Astral installation/release
metadata, Microsoft's image inventory/registry and nodejs.org releases before
selecting candidate artifacts. These are candidates, not approved safe pins:

| Candidate | Verified metadata |
|---|---|
| Microsoft universal 6.1.10 | Ubuntu 24.04; created 2026-10-09; index `sha256:019e9ea0eebbab70fb44c68874f975dbeea6b56faf6ad7f97065fd6bce8b61d2`; amd64 `sha256:8707cdea0e828661a60ffb3739f3d755714b5e497517a5e7eabfd216b55a89e2`; compressed 3.77 GiB |
| Node 24.22.1 linux-x64 tar.xz | Latest LTS in official index; SHA256 `6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6` from official SHASUMS256.txt; October security release |
| uv 0.13.5 linux-gnu tar.gz | Latest stable in GitHub releases and PyPI; asset SHA256 `f68d291c75783122dad58ab77def0e13f3233f358731db5d6d7e8715603b928f` from official release metadata |
| Codex 0.164.0 linux-musl tar.gz | Official release asset SHA256 `90dd0b03b28afcb7fa733a4f73b413db2916a47347efd43fb669cc1c774ee8e4`; official npm latest also 0.164.0 |

Fetched the official tagged Rust lockfiles as data, without building/installing
anything. Queried OSV by exact package/version for **654 registry packages**
from uv and **1,297 registry packages** from Codex, batching up to 500 queries.
There were advisory matches for 13 uv packages and 26 Codex packages. These
are workspace-wide matches, including possibly unused/target-specific/dev
packages; they are not all proven vulnerabilities in a released Linux binary.
Codex also has pinned Git dependencies, whose complete audit remains open.
No complete-clean audit is claimed for either candidate, the image, Node's
bundled npm graph or a managed Python artifact.

Lockfile SHA256 values:

- uv: `3fd592a70bd1c1a83efd3f9191945e57243f26b34a241fe8d4182b5c04258a1b`
- Codex: `7ec2bfabf3b967c00409b85489076f8df3849745d3e469473d88288322adeb4a`

Triaged a concrete blocker rather than treating all matches as exploitable:
uv 0.13.5 locks **h2 0.4.15**, below the fix **0.4.16** for
[RUSTSEC-2026-0258](https://rustsec.org/advisories/RUSTSEC-2026-0258.html)
(unbounded buffering of empty HTTP/2 DATA frames). Its workspace enables
reqwest's `http2` feature; `uv-client` uses that workspace reqwest dependency.
Read `uv-client/src/base_client.rs`: the client builder uses rustls and no
`http1_only` restriction appears in that file. This supports applicability to
the download client; it is source/configuration evidence, not a binary exploit
test. uv 0.13.4 also locks h2 0.4.15. Releases older than 0.13.4 are affected
by the maintainer's separate [GHSA-hq85-5cpj-mr62](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62).
Thus the two current candidates cannot clear the required installation audit.
Other matches, including rustls 0.23.45 and Tokio, require further applicability
analysis if a new candidate is selected; they have not been waived.

The public GitHub API hit a rate limit during metadata reads; used the already
available `gh api` for those read-only release/advisory requests instead. No
authentication flow or account setting was changed. No new tool or executable
archive was downloaded or installed. The installer and devcontainer remain
unimplemented/unchanged. Existing uv was used only for offline/no-sync local
tests and checks; this is not a new uv installation or an audit clearance.

The tests-first step is complete and is being saved/pushed. Implementation
cannot proceed to an installable setup with these candidates under AGENTS.md's
"do not install versions with known applicable vulnerabilities" rule. Resume
by rechecking official patched releases and the complete applicable dependency
graph. A custom patched build would require a separately reviewed scope
decision; none is authorized or prepared here. Do not install an affected
candidate merely to obtain fresh-container evidence. No PROOF/REVIEW, full
make-check result, container rebuild or merge is claimed.

Sources checked:

- https://learn.chatgpt.com/docs/codex/cli
- https://docs.astral.sh/uv/getting-started/installation/
- https://raw.githubusercontent.com/devcontainers/images/main/src/universal/history/6.1.10.md
- https://mcr.microsoft.com/v2/devcontainers/universal/manifests/6
- https://nodejs.org/dist/index.json
- https://nodejs.org/dist/v24.22.1/SHASUMS256.txt
- https://nodejs.org/en/blog/vulnerability/october-2026-security-releases
- https://api.github.com/repos/astral-sh/uv/releases/tags/0.13.5
- https://api.github.com/repos/openai/codex/releases/tags/rust-v0.164.0
- https://registry.npmjs.org/@openai/codex/latest
- https://raw.githubusercontent.com/astral-sh/uv/0.13.5/Cargo.lock
- https://raw.githubusercontent.com/astral-sh/uv/0.13.5/Cargo.toml
- https://raw.githubusercontent.com/astral-sh/uv/0.13.5/crates/uv-client/Cargo.toml
- https://raw.githubusercontent.com/astral-sh/uv/0.13.5/crates/uv-client/src/base_client.rs
- https://raw.githubusercontent.com/astral-sh/uv/0.13.4/Cargo.lock
- https://raw.githubusercontent.com/openai/codex/rust-v0.164.0/codex-rs/Cargo.lock
- https://api.osv.dev/v1/querybatch
- https://api.github.com/repos/astral-sh/uv/security-advisories
- https://api.github.com/repos/openai/codex/security-advisories

### User-directed continuation with existing versions — 2026-10-26

The user instructed "go on with exsting version" after the known setup-tool
warning and inability to verify a fixed official version had been explained.
Recorded the explicit existing-tool exception in ADR 0006 and linked it from
AGENTS.md and the decision log. No general security rule or quality threshold
was lowered. The hypothetical setup deferral was not adopted: all eight new
setup tests and fresh-setup acceptance remain required.

Verified installed tools: uv 0.13.5, Codex CLI 0.164.0, Node 24.22.1. Read the
existing uv ELF `.dep-v0` metadata without executing new code: h2 0.4.15,
rustls 0.23.45 and Tokio 1.53.1 are present. The publisher's stable release
list still ends at 0.13.5, with no prerelease in the ten latest entries. Its
current source at `656d02b614609dd6c982707b6d6c325b6120285b` retains those
dependency versions, so no unverified source build was substituted.

Implemented the approved 52-line Bash installer and pinned image configuration
(61 physical lines combined), within the 100-line amendment bound. The script
rejects unsupported platforms, limits HTTPS downloads and redirects, checks
all three pinned digests before any extraction, and installs tools beneath a
caller-selected directory. The default is the Codespace user's private tool
directory, selected through remoteEnv PATH. No npm lifecycle script or mutable
downloaded shell installer is executed. Documented the setup command in docs/08.

Actual targeted command:

```sh
UV_CACHE_DIR=/tmp/lantern-uv-cache UV_NO_SYNC=1 uv run --offline pytest tests/test_devcontainer_setup.py tests/test_workspace.py -q --tb=line
```

Exit 0: **21 passed** (eight new tests and thirteen existing workspace checks).
All deeper positive/negative installer assertions now execute. Real SHA256,
tar, copy, install, symlink and test-authored executable behavior are checked;
only downloads are substituted with harmless local archives. Ruff check,
format check, `bash -n .devcontainer/setup.sh` and `git diff --check` exited 0.

Started the existing local Compose database with `make db`; it became healthy.
The full make check is running, with output retained at
`/tmp/lantern-m0-setup-make-check.txt`; no completed result is claimed here.

For the fresh-environment verification, started an owned temporary Docker
daemon using existing installed Docker, a private Unix socket and data root
under `/tmp/lantern-m0-docker-ef1ahnj2`. It has no bridge or iptables management.
This avoids consuming the active workspace's limited disk while fetching the
3.77-GiB compressed image. The active Docker daemon and Codespace remain
running. No auth directory, secret environment, account setting, billable
resource, review runner, protected harness or CI file was changed. The image
pull is in progress, not fresh-container proof. Results and cleanup follow.

Full gate completed on the final installer (including the 200,000,000-byte
per-download cap):

```sh
UV_CACHE_DIR=/tmp/lantern-uv-cache UV_NO_SYNC=1 make check
```

Exit **0**, **309 tests passed**, total coverage **95.90723055934515%**.
All ten ordered checks passed, including strict types in 16 source files,
import contracts, deny-list, bandit and the complete installed Python inventory
audit. Every configured critical path is currently "not present", as expected
at this stage; no invented critical-path coverage is reported. The actual
final output is `/tmp/lantern-m0-setup-make-check-final.txt`. Pip-audit's cache
could not be written under the read-only home, but its live advisory check
completed successfully; that cache warning is not an audit bypass. The
acceptance-ID checker separately exited 0 for both bootstrap stories.

Advisory security/test checklist pass, scoped to this setup amendment after
reading docs/02 §9/§17 and docs/07 §1–§2 and the applicable source/tests:

- Security: no new application network surface or research gateway exists in
  this amendment. The developer installer uses only fixed official URLs,
  HTTPS-only redirects, fixed hashes before extraction, bounded retries,
  time/file-size limits, a private temporary directory and quoted paths.
  No token, auth directory or real database credential is copied into the
  fresh environment. The remaining development-tool advisory risk is the
  accepted ADR 0006 exception, not a clean-audit claim. No additional blocker
  was found in this amendment.
- Tests: the positive path runs the real checksum/extraction/installation
  commands on harmless archives and executes the installed test programs;
  the negative cases corrupt the archive bytes without replacing SHA256.
  No unit under test is mocked. The shell download function performs I/O,
  so there is no new pure function requiring a Hypothesis property. Notes for
  independent review: installation reruns/profile PATH behavior should be
  checked in the real fresh environment; the byte cap itself is a curl option,
  not a new claim of an application evidence-capture bound.

Saving this checked implementation candidate before creating its fresh clone.
Fresh-container verification, formal proof and independent review are still
pending; the full gate result alone does not satisfy those steps.
