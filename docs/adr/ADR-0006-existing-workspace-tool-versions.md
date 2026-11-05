# ADR 0006 — Continue with the existing workspace tool versions

Date: 2026-10-26

Status: Accepted by the user's instruction, "go on with exsting version".

## Context and decision

The setup amendment's tests are RED. Progress then stopped because the current
uv release contains a dependency affected by RUSTSEC-2026-0258. The user was
told in plain words that the setup tool has a known security problem, that
installing an affected version conflicts with the project policy, and that no
verified fixed official version had been found. The user explicitly directed
work to continue with the existing version.

Continue the approved M0 setup amendment with the existing tool versions:
uv 0.13.5, Codex CLI 0.164.0 and Node 24.22.1. Pin the official artifacts and
verify their hashes. Reproducing those versions in an owned isolated test
container is part of the approved fresh-setup verification; do not rebuild or
stop the active Codespace. No custom patched build or story split is needed.

This is an explicit exception for these development-tool versions, including
the recorded unresolved transitive advisory matches. They are not certified
free of vulnerabilities. Retain the audit findings and disclose this exception
to the independent reviewer. The uv binary's embedded dependency metadata was
read without executing new code and confirms h2 0.4.15, rustls 0.23.45 and
Tokio 1.53.1. The HTTP/2 advisory concerns possible memory exhaustion from a
malicious peer; it is not evidence that a workspace compromise occurred.
Other source-lockfile matches remain recorded in PLAN-M0, rather than silently
being treated as resolved or as all proven exploitable in these binaries.

The exception does not approve arbitrary vulnerable dependencies, a new tool
version, a weakened package audit, a paid service, an account-setting change,
a merge, or omitting proof/review/fresh-setup acceptance. Python application
dependencies still need the full strict audit; all tests, types, lint, coverage,
deny-list and security gates remain required. Use official sources and keep
downloads limited and authenticated. Revisit these development-tool pins when
a checked upstream fix becomes available; no automatic upgrade is introduced.

The project-wide supply-chain rule remains unchanged except for this explicit
user-directed exception. The previously considered setup deferral was only a
proposal in chat: no story was split, no setup criterion was deferred and no
test was removed.

References: ADR 0002; ADR 0005; PLAN-M0 supply-chain checks;
https://rustsec.org/advisories/RUSTSEC-2026-0258.html .
