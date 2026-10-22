# ADR 0001 — Official Node.js security updates bypass the cooldown

Date: 2026-10-22

Status: Accepted by the user in this session.

Context: AGENTS.md requires a seven-day wait for newly published packages and a
current patched Node.js LTS runtime. The latest official LTS security release,
24.22.1, was released on 2026-10-21, so the two rules needed clarification.
This supplements D21 (the development environment) and the supply-chain rule.

Decision: Node.js security updates may be installed immediately, but only from
official releases downloaded from https://nodejs.org/ . The seven-day wait
continues to apply to everything else, including ordinary Node releases,
Python dependencies, build dependencies, development tools and their transitive
packages. The exception does not permit unofficial builds, alternate mirrors,
unrelated package upgrades, or changes to the container/agent configuration.

Verification: Check nodejs.org release notes and security advisories, select a
patched LTS release and verify the downloaded artifact against its official
checksum before using it. Preserve the existing agent installation; do not
reinstall npm packages merely as part of changing the Node runtime.

References checked 2026-10-22:

- https://nodejs.org/en/download
- https://nodejs.org/en/blog/release/v24.22.1
- https://nodejs.org/en/blog/vulnerability/october-2026-security-releases

Consequences: The immediate Node security update is authorized. No other
dependency cooldown is weakened. Record runtime changes in the story log;
filesystem sandbox approval is still required for writes outside the workspace.
