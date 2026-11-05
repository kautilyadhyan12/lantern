# ADR 0002 — Use checked security fixes without an age delay

Date: 2026-10-23

Status: Accepted by the user in this session.

Context: The fixed certifi and virtualenv releases were blocked by the seven-day
cooldown, while the older eligible versions had current security advisories.
The user explicitly instructed us to continue without the wait while retaining
security checks. This updates the supply-chain policy associated with D21.

Decision: Remove the mandatory age delay for all packages. Before installation,
explain the dependency's purpose, check current advisories for the complete
resolved graph, reject yanked distributions and known applicable vulnerabilities,
and use official package sources with committed version/hash locking. A clean
advisory query is evidence at a point in time, not a guarantee of perfect safety.
If a required query fails, do not treat it as a clean result.

Use uv's explicit exclude-newer = false to remove the previous inherited age
restriction. Keep secure minimum constraints for known fixed releases and update
the lockfile only through uv. The actual resolved graph must be checked before
sync; do not blindly upgrade unrelated direct dependencies.

Node.js remains restricted to official nodejs.org releases, with checksum
verification. Litellm remains prohibited. GitHub authentication must not use
gh auth login or a personal access token in the Codespace. Secrets stay in
environment variables, and no proof, review or acceptance check is waived.

This supersedes ADR 0001 only for its mandatory seven-day wait. Its official
Node.js source restriction remains in force. Update AGENTS.md and the obsolete
cooldown test to reflect the user's changed requirement; preserve the historical
plan logs explaining earlier failures.

References:

- https://docs.astral.sh/uv/concepts/resolution/
- https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2
- https://github.com/pypa/virtualenv/security/advisories
