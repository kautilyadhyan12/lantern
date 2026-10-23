# AGENTS.md — Lantern

Lantern is an open-source intelligence (OSINT) investigation platform. It investigates questions using only public information: the web, news, social posts, satellite images, aircraft and ship tracking, and company and domain records. A brief becomes key questions. Audited tools gather public evidence, and every source used is preserved and hashed. Claims are anchored to exact quotes, and corroboration counts only independent origins. Findings use Admiralty ratings, ICD 203 likelihood terms and rule-based confidence. A report is published only after every sentence has been checked against its citations.

It is a personal, non-commercial project with a public demo for recruiters. The repository is public.

**The user is a beginner.** Explain in plain words, do the housekeeping yourself (05 §1.1), and stop at every approval point below.

Start every session by reading `docs/00_START_HERE.md`. The design docs `docs/0*.md` are the source of truth. If something in them is wrong or missing, say so and propose a decision record in `docs/adr/`. Never silently diverge.

## Where to look

- Product, playbooks, non-goals: `docs/01_PRODUCT_SPEC.md`
- Architecture, data model, egress, gateways, deployment: `docs/02_SYSTEM_DESIGN.md`
- Agent loop, roles, extraction, assessment standard, people rules, evals, costs: `docs/03_AGENT_DESIGN.md`
- External sources, model providers and their terms: `docs/04_DATA_SOURCES.md`
- How we work, Codex setup, the review prompt, CI: `docs/05_ENGINEERING_WORKFLOW.md`
- What to build next (stories, AC IDs): `docs/06_ROADMAP_BACKLOG.md`
- Safety, privacy, legal controls: `docs/07_SAFETY_LEGAL.md`
- Setup and the one-time M0 bootstrap: `docs/08_SETUP.md`
- Why things are as they are: `docs/09_DECISIONS.md`

## The loop (mandatory)

pick → `$plan` → `$tests-first` → `$implement` → `$prove` → `$review` → fix → `$ship` → `$smoke`

- One story per branch (`story/<ID>`) and per session.
- Never commit to `main` directly.
- The one exception is the M0 bootstrap: S0.1 and S0.2 share the branch `story/M0-boot` (`08_SETUP.md` §5).

## Asking first (mandatory — this overrides any instinct to be helpful by starting)

1. "Let's build the next thing" is not permission to build. Say which story is next and why, then stop and wait for a yes.
2. After writing the PLAN, post a short plain-English summary (scope, what gets built, what does not, the size), then wait for a yes before writing tests or code.
3. Never skip, reorder or defer a step of the loop.
   - Each step finishes and is reported before the next one starts.
   - "Prove" means `make prove STORY=<ID>` ran on this exact code and produced the PROOF file. Never claim tests passed without that file or the real command output.
   - "Review" means `make review STORY=<ID>`: a fresh reviewer session in a throwaway copy (05 §4). A review inside your own session does not count.
   - You may never edit `.codex/prompts/t3.md` or `scripts/review.py` except in a story whose approved PLAN says so, and never write PROOF or REVIEW files yourself: only `make prove`, `make review`, or (before S0.4) the by-hand `codex exec … --output-last-message docs/reviews/REVIEW-<ID>.json` command of 05 §4.2 writes them.
   - If a step cannot run because its tool belongs to a later story, stop and ask, unless the skill for that step says exactly what to do.
4. Ask before:
   - merging into `main`
   - changing CI (`.github/`) or the harness (`.codex/`, `.agents/`, `scripts/hooks/`, `scripts/review.py`)
   - splitting or rescoping a story
   - anything that costs money
   - anything touching the user's GitHub account settings

   Pushing a story branch does not need asking. A plan is a proposal, not a decision.
5. Report in plain English, in short sentences. Keep IDs, thresholds and jargon in the files. Say plainly what was done, what was not done, and what needs a decision.

## Housekeeping (do it every time; 05 §1.1)

- At the end of every step: commit on the story branch, then `git push -u origin HEAD`.
- At the end of a session, tell the user: "Everything is saved and pushed. You can close this tab." The codespace stops by itself after 30 minutes idle.
- Secrets come only from environment variables (Codespaces secrets). Never print them. Never create or commit `.env` with real values.
- The repository is public: never commit personal data, captured evidence (`var/`), or secrets.

## Commands

`uv sync` · `make db` · `make hooks` · `make check` · `make prove STORY=<ID>` · `make review STORY=<ID>` · `make evals` (M1+) · `make live` · `make smoke` (M1+)

- Dependencies: `uv add <pkg>` only.
- Supply chain: before adding or updating a dependency, say why it is needed and check current security advisories for it and its resolved dependencies. There is no mandatory 7-day wait; checked security fixes may be installed immediately. Use official package sources, lock exact resolved versions and hashes, reject yanked releases, and do not install versions with known applicable vulnerabilities. Keep the Node.js used by Codex on the latest patched LTS release, using official releases from nodejs.org only. Never add litellm. Never run gh auth login or use a personal access token in the codespace.
- Cassettes: only through `scripts/record_fixture.py`. Use `tool <tool> <case> --args <json>` for one call, or `pytest <test ids>` to record what those tests are missing (HTTP and model). Never hand-write or edit anything under `tests/fixtures/`, `docs/proofs/` or `docs/reviews/`.

## Quality bar (`make check`; never lowered without a recorded decision)

- ruff and ruff format clean · `scripts/lint_custom.py` clean · import contracts clean · dependency deny-list clean · `mypy --strict` clean
- All tests pass.
- Coverage ≥ 85% total and ≥ 95% on critical paths (05 §5.1).
- bandit and pip-audit clean.
- Every AC has a test marked `@pytest.mark.ac("<ID>")` that was RED before implementation.
- From S1.13 on: no unexplained eval regression when prompts, routing, roles, assessment rules or the loop change.
- No new skip or xfail without an issue link, and no new `type: ignore` or `noqa` without a stated reason.
- No `except Exception: pass`.

## Architecture rules

1. The model proposes; code decides. Every model output is one JSON object validated by Pydantic. An invalid output gets one retry with the error, then the step fails. Never parse partially.
2. Steps are stateless. The model sees only views built by `agent/views.py`, with short refs (Q3, S12, C47, F2). Every ref in an output is validated.
3. Every boundary has one choke point:
   - outbound HTTP → `egress.SafeTransport`
   - tool calls → `tools/gateway.py`
   - model calls → `llm/gateway.py` (OpenAI-compatible providers, fallback chains, quotas)

   Budgets, quotas, limits, retries, caching, capture, events and policy live only there, never in adapters or roles.
4. Search results are transient: never store their titles or snippets. Evidence is what Lantern fetches and preserves itself.
5. The fetch tool accepts only URLs already known to the investigation: user input, search results, or links inside captured sources.
6. Confidence comes from `core/assessment.py`, never from model prose. Likelihood uses the ICD 203 terms, and a likelihood term and a confidence level never share a sentence.
7. `core` and `policy` are pure: no network, database, model or filesystem imports. The layer contracts enforce the module map of `02` §5.
8. Pydantic at every boundary. Timezone-aware datetimes only. Async I/O with timeouts. No `time.sleep`, `print` or `shell=True` in `src/`; subprocesses only with argument lists.
9. Every state change writes its event in the same transaction. Logs are structured (`structlog`) and redact secrets and personal data.
10. Errors and refusals say what happened and what to do instead, in plain words. No slogans.
11. Stories stay under ~400 non-test lines. S0.2 alone may use up to 800 handwritten non-test lines under accepted [ADR 0003](docs/adr/ADR-0003-proof-kit-size-and-strict-audit.md); all quality gates remain required. Design changes get a decision record.

## Non-negotiable invariants (each needs a test; any violation is a review blocker)

1. Public data through official APIs or permitted access only: no private accounts, credential sharing, CAPTCHA or anti-bot bypass, or scraping where terms forbid it.
2. No sock puppets and no write actions on any platform.
3. No facial recognition, face matching or biometric inference.
4. No stalking-style profiling.
   - No data brokers or breach data.
   - Ordinary people only through `person_lookup` under `07` §2.2.
   - Never guess accounts from a matching name, username or photo.
   - Never collect a private person's posts or photos into a profile.
   - Never a private person's home, phone, family, contacts, routine or location.
5. No inference of protected traits (religion, caste, ethnicity, health, sexual orientation, political opinion, trade-union membership) about anyone.
6. No investigation whose subject is a minor.
7. Egress is SSRF-safe, identifies itself, respects robots.txt for generic pages, and obeys per-source limits and licences.
8. Every used source is preserved with its sha256; every tool call, model call and policy decision is in the hash-chained event log.
9. Reports never state uncorroborated claims as fact; allegations are attributed; the verification gate decides publication.
10. Retention is bounded and deletion is real.
11. Captured content is untrusted data and can never trigger an action outside policy.
12. Demo visitors never get `person_lookup` or `self_audit`, and never exceed the demo caps (`07` §2.3).

## When unsure

Say so in the PLAN, or ask. Never guess an external API's schema; record a cassette. Never invent prices, limits or terms: check `docs/04_DATA_SOURCES.md` and re-verify online during `$plan`.
