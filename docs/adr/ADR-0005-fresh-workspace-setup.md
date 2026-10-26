# ADR 0005 — Make the saved workspace setup satisfy the security policy

Date: 2026-10-26

Status: Proposed. No configuration, test or acceptance-criterion change is
authorized until the user approves this amendment to PLAN-M0.

## Evidence

The unchanged `.devcontainer/devcontainer.json` selects
`mcr.microsoft.com/devcontainers/universal:2`. Read-only registry inspection
resolved that tag to manifest-list digest
`sha256:dca6a985ffbbc74007a13b6f56ac0fbbc5febae081350b66e865a5549338134b`.
Its amd64 image is version 2.13.1, created 2025-05-06, and has 3.57 GiB of
compressed layers. No image was pulled or executed.

Microsoft's matching [image inventory](https://raw.githubusercontent.com/devcontainers/images/main/src/universal/history/2.13.1.md)
lists Node 20.19.1 and 22.15.0. The repository's post-create command installs
uv and Codex but contains no Node update. The [official Node release index](https://nodejs.org/dist/index.json),
checked today, identifies v24.22.1 (2026-10-20, security release) as the latest
LTS release. The running workspace already has v24.22.1; its manual preparation
does not demonstrate that the saved configuration reproduces it.

This conflicts with AGENTS.md and accepted ADR 0002's latest-patched-LTS rule.
It also exposes a specification conflict: S0.1-AC6 and
`tests/test_workspace.py::test_pack_files_unchanged` require the devcontainer
configuration to remain byte-for-byte unchanged. A rebuild alone does not
correct the saved command or resolve that conflict. This inspection is not a
fresh-container test result or a claim that all other setup requirements fail.

## Proposed decision and scope

Amend the existing bootstrap only to repair fresh-workspace setup before its
joint proof and independent review:

1. Update `.devcontainer/devcontainer.json` and, if needed, one small setup file
   under `.devcontainer/` to use a maintained official image and install checked
   tool versions. Select and record the image digest and exact tool artifacts
   before installation. Obtain Node only from nodejs.org and verify checksums;
   check current advisories for installed tools and resolved dependencies.
   Replace the unchecked download piped to a shell with a reviewed, verified
   installation procedure. No Python runtime dependency is added.
2. Change only S0.1-AC6's initial preservation clause to:
   "The shipped review schema, `.codex/` and `.agents/` are kept unchanged;
   `.devcontainer/` may receive the setup correction approved in ADR 0005."
   Keep the rest of that criterion verbatim. Update its copies in the backlog,
   PLAN-S0.1 and PLAN-M0 and explain the authorized change in their logs.
3. Adjust the existing preservation test only for that approved devcontainer
   exception. Keep byte-for-byte checks on every other protected pack file.
   Add meaningful failing setup tests before implementation, record their RED
   run, then implement and run the required checks. This changes an explicitly
   approved requirement; it does not relabel the original RED evidence.
4. Verify a fresh environment with the approved configuration. Prefer an owned
   isolated container if disk space and isolation permit it. Ask separately
   before rebuilding or stopping the active Codespace or incurring any charge.
   Do not mark fresh-setup acceptance complete without actual evidence.
5. Resume the original joint proof and independent review on the corrected,
   committed code. Include the setup amendment in the review scope.

Expected size: at most 100 additional handwritten non-test lines, with the
combined S0.2 accounting still below its accepted 800-line cap; stop and ask
if that estimate or the approved scope cannot hold. No `.codex/`, `.agents/`,
`.github/`, review-schema or review-runner changes are proposed. No new product
feature, paid service, account setting, PR or merge is included.

## Alternatives and rollback

Preserving the current configuration leaves the security-policy conflict and
fresh-setup acceptance unresolved. Manually preparing each new workspace does
not establish a repeatable saved setup. Neither is accepted silently.

Until approval, retain the current configuration, all tests and criteria, and
keep the bootstrap unfinished. After approval, changes stay on `story/M0-boot`;
main and the active workspace lifecycle remain untouched. Revert ordinary
setup changes if necessary while preserving generated evidence and the logs.

References: D1, D12, D18, D21; ADR 0002; PLAN-M0 execution step 1;
docs/08 §5; S0.1-AC6; AGENTS.md Asking first §4.
