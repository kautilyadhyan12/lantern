# ADR 0003 — Proof kit size exception and strict package auditing

Date: 2026-10-23

Status: Proposed. Requires the user's approval. This does not change policy yet.

Context: S0.2's approved plan estimated roughly 400 handwritten non-test lines.
This proposes a narrow exception to the size rule accompanying D12's workflow,
not a change to its testing, provenance or independent-review requirements.
The check runner, dependency deny-list, coverage gate and Git-tree digest now
work, with 112 targeted tests passing. Including configuration, Make wiring and
the remaining signature stubs, the story has 397 added handwritten non-test
lines relative to S0.1's completed implementation. Generated uv.lock, tests and
process documentation are excluded. The requirement tracer and proof writer
are still unimplemented. Their provenance, validation, redaction and failure
handling need approximately 250 additional lines; the audit correction below
also needs a small helper. The original size estimate was too small.

The planned `pip-audit --local --skip-editable --strict` command also fails
before completing its audit. pip-audit 2.10.1 represents an intentionally skipped
editable package as SkippedDependency, and --strict rejects every such result.
The installed CLI returned exit 1 with `lantern: distribution marked as editable`.
The test's exact command catalogue encodes that invalid combination. It needs
an approved correction; the implementation must not silently weaken the test
or remove --strict.

Proposed decision:

1. Allow this one S0.2 bootstrap story up to 800 handwritten non-test lines.
   The expected final size is approximately 700–750, allowing readable validation
   and error handling. Retain the existing branch and all six acceptance criteria.
   Keep every coverage, lint, type, security, proof and independent-review gate.
   Other stories retain the existing approximately 400-line rule. If accepted,
   record this narrow exception in AGENTS.md and docs/05 before further code.
2. Add scripts/audit_dependencies.py and tests/test_audit_dependencies.py. The
   helper inventories the installed environment, validates package names,
   versions and editable metadata with Pydantic, and writes exact pins into a
   temporary requirements file. It may omit only Lantern's verified local
   editable distribution; any other editable package or invalid inventory fails.
   Invoke the installed pip-audit with --strict --no-deps --disable-pip,
   --progress-spinner off, --timeout 30 and -r <temporary requirements>.
   Use fixed argument lists, bounded waits, safe temporary-file cleanup and
   sanitized errors. No registry install/resolution, fixes, advisory ignores or
   tolerated collection/network failures. All installed third-party packages
   remain audited. Existing uv.lock hashes remain the installation authority.
3. Replace only the invalid audit entry in the exact shared-command test with
   `uv run python scripts/audit_dependencies.py`. Update the Make failure-injection
   test's final command label to the helper's path, retaining all ten steps and
   all per-step failure cases. Add the helper to standalone-CLI checks. Add
   failing tests before implementation for complete inventory, the single local
   first-party exception, unexpected editable packages, malformed metadata,
   strict CLI arguments, audit/network failure propagation and cleanup. Do not
   change coverage thresholds, remove existing assertions or loosen fail-fast
   behavior. Record the additional RED run before building this helper.

Read-only diagnostic evidence: an exact-pinned snapshot of all 74 installed
third-party distributions, excluding only the verified local editable Lantern,
was audited with the proposed strict CLI arguments. The command exited 0 with
`No known vulnerabilities found`. This diagnostic is not a make check, proof,
review or implementation of the helper. PyPI/OSV, source, hash and yanked-status
checks separately passed for all 75 registry packages in the complete lockfile
before sync (the platform-specific lock includes one extra package).

Alternative: split the job into a gate story (S0.2-AC1/2/5/6) and a provenance
story (S0.2-AC3/4), each with its own approved plan, tests and full workflow.
That requires backlog IDs, bootstrap documentation and test-marker updates;
the one-time bootstrap would need to explicitly cover three stories. No such
split is performed here. The proposed single-story size exception retains the
existing requirements and joint S0.1/S0.2 proof/review arrangement.

References:

- docs/05_ENGINEERING_WORKFLOW.md §1 (story size), §2 and §5 (quality).
- docs/plans/PLAN-S0.2.md, Design, Size and Test plan.
- .agents/skills/implement/SKILL.md §3 (approval before correcting a wrong test).
- https://github.com/pypa/pip-audit/blob/v2.10.1/pip_audit/_cli.py
- https://github.com/pypa/pip-audit/blob/v2.10.1/pip_audit/_dependency_source/pip.py
- https://github.com/pypa/pip-audit#usage
