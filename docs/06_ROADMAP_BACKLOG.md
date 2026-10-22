# 06 — Roadmap and Backlog

Pack 3.0 · written 2026-10-22 · status: source of truth for what to build next

Every story runs through the loop in `05_ENGINEERING_WORKFLOW.md`. AC IDs are stable; tests carry `@pytest.mark.ac("<ID>")`. Sizes are non-test lines of code: **S** ≤ 150, **M** ≤ 300, **L** ≤ 400 (above 400: split before building). Stories within a milestone are listed in dependency order. Time estimates assume one developer driving an AI coding agent part-time; they are guidance, not promises.

## Milestones at a glance

| Milestone | Outcome | Stories | Rough time |
|---|---|---|---|
| M0 Foundation | Empty folder → tooling, proof, guards, review and CI kits; the workflow running | S0.1–S0.5 | 1–2 weeks |
| M1 Walking skeleton | `lantern run "<brief>"` → cited report (web search + fetch), replayable, with evals | S1.1–S1.13 | 4–6 weeks |
| M2 Trustworthy core | Durable runs, policy gate, independence, assessment standard, ACH, verification gate, preservation, news/fact-check sources, evidence bundle, evals v1, retention | S2.1–S2.12 | 5–7 weeks |
| M3 Workspace | Web app for briefs, live runs, approvals, reports, evidence review | S3.1–S3.7 | 4–5 weeks |
| M4 Packs | Earth observation · Media · People · Movement · Organisations · Infrastructure · Social · Regional India | epics, decomposed with `$plan-epic` | 2–4 weeks each |
| M5 Operate | Public demo for recruiters, monitors, backups, cost and quality dashboards | epics | as needed |

**Milestone exit rule**: a milestone closes when all its stories are merged, `make check` and CI are green on `main`, live evals (from M1) show no unexplained regression, and the user has run the milestone demo (listed under each milestone).

---

## M0 — Foundation

M0 starts from a GitHub repository that contains only this plan, opened in a Codespace (`08_SETUP.md`). S0.1 and S0.2 are built together as a one-time bootstrap, because the proof tool does not exist until S0.2 (`08_SETUP.md` §5). From S0.3 on, every story follows the normal loop.

### S0.1 Repository skeleton, dev container and tooling (size M)
Refs: 02 §5, §20; 05 §2.1, §3.
- S0.1-AC1 `uv sync` on a fresh clone succeeds (Python 3.12 pinned in `.python-version`, `uv.lock` committed); `make check` runs `ruff check`, `ruff format --check`, `scripts/lint_custom.py`, `mypy --strict` and the offline `pytest` suite, and is green with one placeholder test; `make db` and `make db-down` start and stop the compose database. (S0.2 extends `make check`.)
- S0.1-AC2 `pyproject.toml` (uv project `lantern`, src layout, console script `lantern`) carries the tool configuration of 05 §2.1; a test asserts each key.
- S0.1-AC3 `docker compose up db` starts Postgres 16 with pgvector (current `pgvector/pgvector` pg16 tag, verified in the PLAN) with a healthcheck, bound to `127.0.0.1:${LANTERN_DB_PORT:-5434}`; `config.Settings` reads `LANTERN_DATABASE_URL` as a secret and accepts only the `postgresql+asyncpg` driver; `lantern db upgrade` applies an empty baseline Alembic migration. The e2e test uses the compose database and fails with a pointer to `make db` when it is down.
- S0.1-AC4 `.pre-commit-config.yaml` uses only local hooks run through `uv run`: end-of-file and trailing-whitespace fixers, ruff, ruff format, mypy, detect-secrets with a committed baseline; `make hooks` installs them.
- S0.1-AC5 `scripts/lint_custom.py` reports each forbidden pattern of 05 §2.1 (one test per pattern, with allowed variants) and passes clean code; property test: it never raises on valid Python.
- S0.1-AC6 The files shipped with the pack (`.devcontainer/devcontainer.json`, `scripts/review_schema.json`, `.codex/`, `.agents/`) are kept unchanged; the dev container still builds a working Codespace after S0.1: Python 3.12, uv, Docker inside the container, Node LTS, the GitHub CLI and the Codex CLI; `make check` passes inside it. `.gitignore` covers `.env`, `.venv/`, `var/` and tool caches; `.env.example` lists every setting with placeholders; a test asserts no `.env` file is tracked.
- S0.1-AC7 `README.md` explains what Lantern is in plain words and how to open it in a Codespace, without secrets or personal data.

### S0.2 Proof kit (size L)
Refs: 05 §2, §5.
- S0.2-AC1 `make check` runs, in this order, stopping at the first failure: `ruff check`, `ruff format --check`, `scripts/lint_custom.py`, `lint-imports` (layer contracts of 02 §5, covering only packages that exist), `mypy --strict`, the offline `pytest` suite with coverage, `scripts/coverage_gate.py`, `scripts/check_dependencies.py`, `bandit`, `pip-audit`. It exits 0 only when every step passes.
- S0.2-AC2 `scripts/coverage_gate.py` reads the coverage JSON report and fails when total coverage is below `coverage_total` or any existing path in `critical_paths` is below `coverage_critical` (all three read from `[tool.lantern.quality]` in `pyproject.toml`); configured paths that do not exist yet are listed as "not present", not failed.
- S0.2-AC3 `scripts/check_acceptance_ids.py <ID> [<ID> …] --backlog <path>` collects the AC IDs listed under each given story's heading in the backlog file, scans `tests/` for `@pytest.mark.ac(...)` without importing test modules, prints an AC → tests table, and fails when one of those ACs has no test or any test anywhere references an AC ID that appears nowhere in the backlog.
- S0.2-AC4 `scripts/prove.py <ID> [--ac-stories <ID> …]` (and `make prove STORY=<ID> [AC_STORIES="…"]`) refuses to run while tracked files outside `docs/` have uncommitted changes; otherwise it runs every `make check` step and `check_acceptance_ids.py` for the AC stories (default: `<ID>` itself), records all of them even after a failure, and writes `docs/proofs/PROOF-<ID>.md` with commit SHA, the code-tree hash (sha256 over the `git ls-tree -r HEAD` entries outside `docs/`, computed by `scripts/code_tree.py`, which accepts extra excluded prefixes), UTC time, platform, and for each step: command, exit code, duration, key numbers and the last 30 lines of output, ending in `RESULT: PASS` or `RESULT: FAIL`; it exits non-zero on FAIL. Tested with a stubbed step runner.
- S0.2-AC5 `[tool.lantern.quality]` sets `coverage_total = 85`, `coverage_critical = 95` and `critical_paths` = the paths listed in 05 §5.1; coverage measures `src/lantern` and `scripts`.
- S0.2-AC6 `scripts/check_dependencies.py` fails when `uv.lock` contains a package on its deny-list (face-recognition and face-embedding libraries, invariant 3 of 07 §1) and passes otherwise.

### S0.3 Agent guard, edit hook and command rules (size M)
Refs: 05 §3.
This story creates harness files (`.codex/hooks.json`, `scripts/hooks/`); once its own hooks are active, its sessions run with `LANTERN_ALLOW_HARNESS_EDITS=1`.
- S0.3-AC1 `scripts/hooks/guard_shell.py` (PreToolUse hook on the coding agent's shell tool) reads the hook JSON from stdin and exits 2 with a plain-words reason for: force pushes in any spelling (`--force`, `-f`, `--force-with-lease`, a `+<ref>` refspec, git global options such as `-C <dir>` before the subcommand); pushing to `main`; `git reset --hard`; `git clean -f…`; `rm -rf`; `pip install` (including `python -m pip` and `uv pip`); a download piped into a shell; writes into `tests/fixtures/`, `docs/proofs/` or `docs/reviews/` (redirection, `cp`, `mv`, `tee`, `sed -i`, `dd of=`) by anything other than the sanctioned writers (`scripts/record_fixture.py`, `scripts/prove.py`, `scripts/review.py`, and `codex exec … --output-last-message docs/reviews/REVIEW-<ID>.json` for by-hand reviews); writes into the harness (`.codex/`, `.agents/`, `.github/`, `scripts/hooks/`, `scripts/review.py`) unless `LANTERN_ALLOW_HARNESS_EDITS=1` is set in the hook's own environment; and `LANTERN_RECORD_FIXTURES=1` outside `scripts/record_fixture.py`. The same path rules apply to file edits made with the agent's edit tool (the hook payload's file paths). It checks every segment of chained commands, `$(…)` and backticks; It checks every segment of chained commands, `$(…)` and backticks; heredoc bodies are data, not commands; unparseable input exits 2 (fail closed). The PLAN records a real sample of the hook payload from the installed Codex version. Table-driven tests plus property tests.
- S0.3-AC2 The guard allows ordinary development commands (table: `uv run pytest`, `make check`, `make prove STORY=S0.3`, `make review STORY=S0.3`, `git status`, `git diff`, `git add` and `git commit` of PROOF and REVIEW files, `git push -u origin HEAD` on a story branch, `uv add httpx`, reading protected folders with `cat` or `grep`, a harness edit when `LANTERN_ALLOW_HARNESS_EDITS=1` is set) and answers in under 1 second.
- S0.3-AC3 `scripts/hooks/post_edit.py` (PostToolUse hook on file edits) runs `ruff format` and `ruff check --fix` on an edited Python file and exits 2 with a summary of at most 40 lines when problems remain, 0 otherwise; non-Python files exit 0 immediately.
- S0.3-AC4 `.codex/hooks.json` (or the `[hooks]` table in `.codex/config.toml`, whichever the installed Codex documents) registers both hooks; `.codex/rules/default.rules` holds the command rules of 05 §3.2; a test parses both files and checks that every hook command points to an existing script, and `codex execpolicy check` confirms each rule's example commands (run in the PLAN, output pasted).
- S0.3-AC5 A test checks that every skill under `.agents/skills/` has valid frontmatter (`name` matches its folder, `description` present) and that `.codex/prompts/t3.md` equals the fenced prompt in 05 §4 followed by one newline.

### S0.4 Review kit (size M)
Refs: 05 §4.
- S0.4-AC1 `scripts/review.py <ID> [--base <ref>]` (and `make review STORY=<ID>`) refuses a dirty tree; creates a throwaway git worktree of HEAD outside the repository; builds the reviewer prompt from `.codex/prompts/t3.md` replacing `{STORY}`, `{STORY_SLUG}` (lower case, dots → underscores), `{ROUND}` (1 + the number of existing `tests/review/test_<slug>_r*_adversarial.py` files) and `{BASE}`; runs a fresh headless reviewer session (`codex exec`) in that worktree as described in 05 §4.2; validates the final JSON against `scripts/review_schema.json` (shipped with the pack); checks `head_sha` equals HEAD; adds `code_tree` (code-tree hash excluding `docs/` and `tests/review/`); writes `docs/reviews/REVIEW-<ID>.json`; copies only the new `tests/review/` file back; deletes the worktree; exits 0 for APPROVE, 1 for REQUEST_CHANGES, 2 for invalid output. Tested with a fake reviewer executable.
This story edits the harness (`scripts/review.py`), so its sessions run with `LANTERN_ALLOW_HARNESS_EDITS=1` (05 §3.3).
- S0.4-AC2 `scripts/review.py --print-prompt <ID> [--base <ref>]` prints the fully substituted prompt and exits, so a manual review uses exactly the same text.
- S0.4-AC3 `review.py` reports every file the reviewer changed in the worktree outside `tests/review/` (they are discarded with the worktree) and records them in the REVIEW file's notes.

### S0.5 Continuous integration (size S)
Refs: 05 §8.
This story edits `.github/`, so its sessions run with `LANTERN_ALLOW_HARNESS_EDITS=1`.
- S0.5-AC1 `.github/workflows/ci.yml` (template in 05 §8.1; created with the user's approval) runs on pull requests and on pushes to `main`: `uv sync --frozen` then `make check`, on `ubuntu-latest`, with a Postgres 16 + pgvector service for the e2e tests. It is green on the PR that adds it.
- S0.5-AC2 The workflow passes `actionlint` (a CI step) and pins every third-party action to a full commit SHA.
- S0.5-AC3 A `review-artifacts` CI step (`scripts/check_review_artifacts.py --pr-title <title>`, which takes the story ID from the PR title's `<ID>:` prefix) fails unless `docs/proofs/PROOF-<ID>.md` ends `RESULT: PASS` and its code-tree hash equals the PR's code tree excluding `docs/`, and `docs/reviews/REVIEW-<ID>.json` says APPROVE and its `code_tree` equals the PR's code tree excluding `docs/` and `tests/review/`. The title is passed through an environment variable, never interpolated into the shell. Unit-tested.
- S0.5-AC4 `.github/pull_request_template.md` exists with: story ID, summary, AC → tests table, risks, rollback, checklist.
- S0.5-AC5 Branch protection on `main` (PR required, `check` required, linear history, no force pushes) is configured by the user following 05 §8.3, and confirmed in the PLAN by a read-only API query.

**M0 demo**: open a PR for S0.5 and watch CI go green; run `make prove STORY=S0.5` and a fresh review; merge.

---

## M1 — Walking skeleton

Goal: the thinnest complete slice of the real product. `lantern run "<objective>" --purpose research` plans questions, searches the web, fetches and preserves pages, extracts quote-anchored claims, assesses each question, and writes a cited report — replayable offline from recordings, measured by evals. No durability, no web UI, minimal policy, no approvals (so no premium tools). The eval rules of 05 §2 apply from S1.13, when the harness exists.

### S1.1 Core domain (size M)
Refs: 02 §5–6, 03 §8.
- S1.1-AC1 `core.refs` parses and formats refs of kinds Q, S, C, F, H, E; rejects malformed refs; `next_ref` allocates the next number for a kind. Property: `format(parse(r)) == r`.
- S1.1-AC2 `core.scales` defines Reliability A–F, Credibility 1–6, Likelihood (the seven ICD 203 terms with ranges, ordered) and Confidence (low, moderate, high). Golden test of the likelihood table.
- S1.1-AC3 `core.models` defines Pydantic models for Brief, Question, SourceRecord, Claim, Finding and the sentence-structured ReportDraft; naive datetimes are rejected; refs are typed; text length limits are enforced.
- S1.1-AC4 `core.text` normalises text (NFKC, quote marks and dashes, whitespace, zero-width characters) with an offset map; `find_quote(text, quote)` returns the original-text span or None. Properties: for any span of the original text cut at grapheme-cluster boundaries, `find_quote` returns a span whose original text normalises to the same string as that span; a string absent from the normalised text is never found.
- S1.1-AC5 `core.budget`: reserve fails when an estimate exceeds what remains in any dimension; settle releases the unused part; the soft-stop threshold is 85%. Properties: once spend has reached the budget in any dimension, every further reservation fails; settling more than was reserved is reported as an overspend.
- S1.1-AC6 `lantern.core` is in the import contracts and imports no I/O library.

### S1.2 Ledger and event log (size L)
Refs: 02 §6, §14.
- S1.2-AC1 An Alembic migration creates the M1 tables of 02 §6 (investigations, questions, known_urls, search_log, sources, claims, claim_questions, findings, reports, runs, tool_calls, llm_calls, events) with constraints and indexes; upgrade → downgrade → upgrade round-trips on a fresh database.
- S1.2-AC2 Typed async repositories (create, get, list, update) for investigations, questions, sources, claims, findings and reports. Property: a domain model written and read back is equal.
- S1.2-AC3 Every repository write appends its event in the same transaction; an injected failure in the event append rolls back the write.
- S1.2-AC4 `EventLog.append` and `EventLog.verify` implement per-investigation hash chains (02 §14); verify detects a modified payload, a deleted row and a reordered row, naming the first broken sequence number.
- S1.2-AC5 The application database role cannot UPDATE or DELETE `events` (test connects as that role); a setup command creates the role and grants for development.
- S1.2-AC6 Refs are unique and gap-free per investigation under concurrent inserts.

### S1.3 Egress: SSRF-safe transport (size L)
Refs: 02 §9.
- S1.3-AC1 `egress.ipclass` blocks private, loopback, link-local, CGNAT, multicast, unspecified, reserved and documentation ranges, IPv4-mapped and embedded IPv6 forms, and cloud metadata addresses; integer, hex, octal and short IPv4 spellings normalise before classification. Property tests per network.
- S1.3-AC2 `SafeTransport` resolves every address, refuses if any is blocked, and pins the connection to the validated address while Host header, SNI and certificate checks use the hostname. A rebinding test (resolver answers public, then private) never connects to the private address.
- S1.3-AC3 Redirects are followed manually (at most 5) and every hop is re-validated; redirects to 169.254.169.254, to private hosts or to non-HTTP schemes are refused.
- S1.3-AC4 Connect, read and total timeouts and a streaming size cap (default 10 MB) abort slow or oversized responses with typed errors.
- S1.3-AC5 Every request carries the configured User-Agent; a per-host token bucket (injectable clock) enforces rate and concurrency; hosts are independent.
- S1.3-AC6 Generic fetches consult robots.txt (protego, 24-hour cache per host); disallowed URLs are refused with a typed error; a robots.txt 4xx means allowed, 5xx or timeout means not allowed for that attempt.

### S1.4 Capture and fetch (size M)
Refs: 02 §10.
- S1.4-AC1 `BlobStore.put` stores bytes content-addressed under the data directory, atomically and idempotently; no path component comes from input (traversal test).
- S1.4-AC2 `extract_text` handles HTML (trafilatura: title, author, date, main text, links), PDF (pypdf) and text/JSON (charset detection); output is normalised; extraction failures are returned as typed results, never raised.
- S1.4-AC3 `canonical_url` and `registrable_domain` (bundled suffix list, no network) are pure and idempotent (property tests).
- S1.4-AC4 `capture.fetch_page(url)` fetches through SafeTransport and returns a SourceDraft (blob hash, text, metadata, links); HTTP errors map to typed failures; non-text content is stored with `text = null`. (S1.5 registers it as the `web.fetch` tool.)

### S1.5 Tool gateway (size L)
Refs: 02 §7.2, §8.
- S1.5-AC1 The Tool protocol and registry generate each tool's argument schema (shown to the model in the tool menu) from its args model; a tool whose schema breaks structured-output rules (recursion, open objects) or whose `side_effects` is not `"none"` is rejected at registration.
- S1.5-AC2 The gateway applies the order of 02 §7.2: vetting (playbook tool list, restrictions, read-only), URL provenance (fetch only known URLs), duplicate check by `args_hash` (other tools return the earlier outcome; search tools return "already searched" without stored results), global cache for immutable lookups (never search tools), budget reservation, premium-tool refusal (approvals arrive in S2.1), limiter and breaker, execution, capture, settlement, `tool_calls` row and events. Each stage has a test with a fake tool.
- S1.5-AC3 A call whose estimate exceeds the remaining budget is refused before any network I/O (zero requests observed).
- S1.5-AC4 The breaker opens after 5 consecutive failures per `rate_key` and half-opens after the cooldown (fake clock); only 429, 5xx and timeouts are retried, with jittered capped backoff.
- S1.5-AC5 Search tools return transient hits; only `search_log` (query, count) and hashed URLs in `known_urls` are persisted. A test scans every table and the blob store for hit titles and snippets and finds none.
- S1.5-AC6 One structured log line per call with tool, version, args_hash, status, latency_ms, cost_usd, source_count and cached.
- S1.5-AC7 `web.fetch` is registered as a free, read-only tool wrapping `capture.fetch_page`; the gateway's URL-provenance check applies to it.

### S1.6 HTTP recording and replay (size M)
Refs: 02 §9.3, 05 §6.
- S1.6-AC1 `scripts/record_fixture.py tool <tool> <case> --args <json>` runs one real call and writes sanitised exchanges with a provenance header to `tests/fixtures/cassettes/http/<tool>/<case>.jsonl`; `scripts/record_fixture.py pytest <test ids>` runs those tests in record mode and records only the cassettes they are missing (`--refresh` re-records existing ones).
- S1.6-AC2 Replay serves exchanges by request fingerprint; a missing exchange raises `CassetteMiss` and never reaches the network.
- S1.6-AC3 `scripts/check_fixture_signatures.py` fails on cassettes without a valid provenance header, with a `tool_version` different from the registered tool, or containing values matching configured secret patterns; it passes on valid cassettes.
- S1.6-AC4 Property: no configured secret header or query value survives sanitisation.
- S1.6-AC5 `make live` runs the tests marked `live` (real APIs, tiny quotas, schema-drift checks); `make check` never runs them.

### S1.7 Web search (size M)
Refs: 02 §8.1, 04 §2.
- S1.7-AC1 `search.web` has a provider interface with Tavily (default, free tier) and Brave (optional) adapters chosen by configuration; a failing provider falls back to the next configured one; a missing key disables a provider with a clear message.
- S1.7-AC2 Contract tests replay cassettes for each provider, including an empty result and a 429.
- S1.7-AC3 Hits are normalised (title, canonical URL, snippet, timezone-aware `published_at` or null, provider, rank) and de-duplicated by canonical URL.
- S1.7-AC4 Each provider's cost estimate equals its configured price (table test); `search_log` records query, language and result count.

### S1.8 Model gateway (size L)
Refs: 02 §7.3, §11; 03 §4–6, §14; 04 §1.
- S1.8-AC1 `structured(role, prompt, inputs, Output)` returns a validated Pydantic instance: the gateway asks for `json_schema` output when the chosen entry supports it, else `json_object`, else plain JSON in the prompt; the whole reply must parse as one JSON object; refs in the output are validated against the investigation; an invalid output gets one retry with the validation error appended, then raises `SchemaFailure`. Tested with fake providers of each capability.
- S1.8-AC2 `actions(role, prompt, inputs, tools)` returns validated tool calls from a structured action list: each call's `args` is validated against that tool's `args_model`; unknown tools are rejected; the number of calls per step is capped per role.
- S1.8-AC3 `src/lantern/data/models.yaml` (the model catalogue) is validated at startup: each `provider:model` entry has context window, prices with the date checked, free-tier limits, output capabilities, a `free | trial | paid` class and a training-on-prompts flag; tiers are ordered lists of entries; routing maps role → tier with per-investigation overrides; unknown roles or entries fail at startup. The PLAN re-verifies every starting entry of 03 §5 on the providers' pages.
- S1.8-AC4 Fallback and quotas: the gateway skips entries without quota (requests and tokens per day, counted in `llm_quota`) or with an open breaker; on 429 it honours `Retry-After` and moves to the next entry; when every entry is exhausted the step fails with a `QuotaExhausted` error naming the providers and when they reset. This story adds the `llm_quota` table migration. `trial` entries are never used when demo mode is on; `paid` entries only when a key and a daily dollar cap are configured. Fake-clock tests.
- S1.8-AC5 Cost is computed from catalogue prices and response usage (cached and uncached input where reported, output); free entries cost $0 but still count tokens and requests; budget is reserved before and settled after; one `llm_calls` row (provider and model included) and one event per call.
- S1.8-AC6 Prompts load from `llm/prompts/<role>/<name>.v<N>.md` with `_common.md` prepended and laid out as in 03 §4.4 (test inspects the request body).
- S1.8-AC7 Model cassettes record (through `scripts/record_fixture.py pytest …`) and replay by a request hash that excludes the provider; a miss raises `CassetteMiss`; 5xx and timeouts are retried with backoff before falling back.

### S1.9 Claim extraction (size L)
Refs: 03 §7.
- S1.9-AC1 Extractor prompt v1 and the `ClaimDraft` schema; long texts are chunked on paragraph boundaries with overlap; one model call per chunk.
- S1.9-AC2 Quotes are anchored by exact match after normalisation; unanchored claims are dropped and counted; tests replay extractions over five recorded sources (news article, PDF, social-style post, registry-style record, non-English article).
- S1.9-AC3 Credibility comes from the rule table in 03 §7 step 3, never from the model (table test).
- S1.9-AC4 The protected-trait screen drops claims that attribute a protected trait to an individual (table of examples, including non-English).
- S1.9-AC5 Record claims are generated by code from source metadata with record reliability.
- S1.9-AC6 Claims link to questions from `question_refs`; duplicates within a source and across chunk overlaps are removed.

### S1.10 Playbooks, planner and loop (size L)
Refs: 03 §2–3; 07 §3.1.
- S1.10-AC1 The playbook schema (03 §3) is validated at load; an invalid file fails with the path of the error; `research` v1 ships with `approvals: {plan_review: false, premium_tools: true}` and no premium tools.
- S1.10-AC2 The planner produces a frame of questions (kind, priority, answer criteria) stored as Q refs, within playbook limits.
- S1.10-AC3 `runner/loop.py` implements question selection (pure, property-tested) and every stop condition of 03 §2.1, each tested with fake roles.
- S1.10-AC4 Deterministic policy pre-rules (07 §3.1) run before planning; a matching objective is denied with a reason and no model call (table test).
- S1.10-AC5 `lantern run "<objective>" --purpose <p>` creates the investigation, runs it in-process, and prints progress and spend.

### S1.11 Researcher and assessor v0 (size L)
Refs: 03 §2, §5, §8.6.
- S1.11-AC1 The researcher proposes at most 4 tool calls per step or declares done; transient hits are triaged into at most 8 fetches within the same step; refusals from the gateway are shown to the next step.
- S1.11-AC2 The assessor's output is validated; cited refs must be linked to the question; confidence v0 counts distinct registrable domains and the best rating (full independence arrives in S2.3); the likelihood clamp of 03 §8.6 applies.
- S1.11-AC3 Findings are versioned (`is_current`), storing both the proposed and the clamped likelihood.
- S1.11-AC4 Question status transitions (answered, unanswerable, attempt cap) follow 03 §2.1.

### S1.12 Report v0 and golden end-to-end test (size L)
Refs: 03 §10.
- S1.12-AC1 The writer produces a sentence-structured report following the playbook outline, with non-factual sentences flagged.
- S1.12-AC2 Deterministic citation checks run: every factual sentence cites at least one claim, and every cited ref exists and is active; failing sentences are removed and listed. (The language lint and the model verifier arrive in S2.6.)
- S1.12-AC3 Markdown and self-contained HTML renderers; citations open claim cards with quote, source and archive information; all evidence text is escaped (XSS test).
- S1.12-AC4 `lantern report <inv> --format md|html|json`, `lantern status <inv>` and `lantern show <inv> [questions|sources|claims|findings]`.
- S1.12-AC5 Golden test: a full `research` run replayed from cassettes produces a report in which every factual sentence cites at least one active claim and every cited content claim's quote matches its source's stored text at the recorded offsets; spend stays within budget; the event chain verifies.
- S1.12-AC6 `make smoke` replays the golden investigation offline against a fresh database, renders its HTML report and verifies the event chain; it exits non-zero on any failure.

### S1.13 Eval harness v0 (size L)
Refs: 03 §12.
- S1.13-AC1 Eval-world loader and eval-mode tool backends: BM25 search over world documents, fetch by URL (unknown → 404), records by tool and args.
- S1.13-AC2 The case runner executes a case in live or replay mode, applies the deterministic checks (answers, `must_not_assert`, `must_not_emit`, `must_not_fetch`, cost, tool calls, citation precision) and writes `evals/results/<timestamp>/<case>.json`.
- S1.13-AC3 The judge (strong tier, rubric file) scores reports 0–100 with a short rationale, through the model gateway.
- S1.13-AC4 `uv run python -m evals compare --baseline evals/baseline.json` exits non-zero on any pass → fail change or a mean judge drop above 2; `make evals` runs every case in live mode and then the comparison.
- S1.13-AC5 Three cases ship (plain, trap, injection canary) with their worlds; the first baseline is recorded.

**M1 demo**: `lantern run "What is publicly known about <a real, non-sensitive public topic>?" --purpose research` with real keys, then open the HTML report and click through citations to the preserved quotes; run `make evals` and read the scores.

---

## M2 — Trustworthy core

### S2.1 Durable runs (size L)
Refs: 02 §12.
- S2.1-AC1 The PLAN records a time-boxed spike proving DBOS Transact (or the fallback in 02 §12) on: async steps, recovery after a killed worker, durable waits, cancellation — in the codespace and in CI.
- S2.1-AC2 Every tool call, model call, clock read and random choice in the loop happens inside a checkpointed step; a run killed mid-way and restarted completes without repeating any paid call (call counts equal an uninterrupted replay). One exception: a search whose triage step was interrupted is run again, because its results are never stored; the repeat is logged.
- S2.1-AC3 Replaying a golden run twice yields identical event-type sequences.
- S2.1-AC4 Approvals (plan review, premium tool calls, budget raise) wait durably; `lantern approve|deny <inv> <approval>`; autonomous mode skips plan review and auto-denies premium-tool and budget approvals.
- S2.1-AC5 `lantern worker` executes queued runs with a per-worker concurrency limit; `lantern cancel` stops at the next step boundary and publishes a partial report.
- S2.1-AC6 `make smoke` also starts a worker, kills and restarts it mid-run, and checks that the run completes without repeated paid calls (apart from the logged search exception in S2.1-AC2).

### S2.2 Policy gate (size L)
Refs: 07 §2–4.
- S2.2-AC1 The gatekeeper (fast tier) returns a PolicyAssessment; the decision is the strictest of pre-rules and gatekeeper (pure combine function; table test over at least 30 briefs with recorded responses).
- S2.2-AC2 `needs_attestation` puts the investigation in `awaiting_attestation`; no run can start until `lantern attest <inv>` records the attestation event (a status, not an in-run approval).
- S2.2-AC3 Restrictions persist and the gateway enforces them.
- S2.2-AC4 Person-pivot rule: a call targeting a person not cleared for this brief is refused unless evidence shows a public figure acting in a public role; refusals are logged and shown to the researcher.
- S2.2-AC5 Output post-checks on claims and report sentences catch protected traits, private location or contact details, and indicators that a subject is a minor; a minor indicator stops work on that subject and flags the investigation.

### S2.3 Independence and contradictions (size M)
Refs: 03 §8.4–8.5.
- S2.3-AC1 Origin keys and near-duplicate merging (MinHash ≥ 0.8). Properties: idempotent and order-independent.
- S2.3-AC2 Claims attributed to the same speaker share an origin across outlets.
- S2.3-AC3 Structural contradictions (same subject and predicate, different values, or times that differ beyond both precisions) are detected and offered to the assessor.
- S2.3-AC4 Credibility 1 and 5 are set only by code and recomputed on every evidence change.

### S2.4 Assessment standard v1 (size M)
Refs: 03 §8.6.
- S2.4-AC1 Evidence profile and confidence rules as pure functions with golden tables. Properties: an added independent supporting origin never lowers confidence; an added stronger contradiction never raises it.
- S2.4-AC2 The likelihood clamp, the contested cap and the negative-search phrasing rule are enforced.
- S2.4-AC3 Evidence changes (claim rejected, rating overridden, new sources) recompute profile, confidence and clamp without model calls and log events.
- S2.4-AC4 Allegations stay attributed and are not upgraded without independent confirmation rated B or better.

### S2.5 Analysis of Competing Hypotheses (size M)
Refs: 03 §9.
- S2.5-AC1 The ACH analyst returns 2–5 hypotheses including the claim as stated and an alternative, plus ratings for diagnostic claims.
- S2.5-AC2 Weighted-inconsistency scoring and diagnosticity are pure. Property: adding an inconsistent rating never improves a hypothesis.
- S2.5-AC3 Contested findings follow the margin rule; the matrix appears in the report appendix.

### S2.6 Verification gate (size M)
Refs: 03 §10.
- S2.6-AC1 The verifier checks sentences in batches with their cited claim cards; verdicts are validated.
- S2.6-AC2 One repair round; remaining unsupported sentences are removed and listed; publication only when none remain; `citation_precision` is recorded.
- S2.6-AC3 The language lint (likelihood phrases match finding labels, no likelihood term and confidence level in one sentence, forbidden absolutes, attributed allegations) passes table tests including negative cases.
- S2.6-AC4 If the verifier fails, the report is saved as `needs_review` and never published.

### S2.7 Preservation (size M)
Refs: 02 §10; 04 §3.
- S2.7-AC1 Every captured HTTP exchange is written as WARC request/response records in per-investigation files; WARC payload hashes match the blob store.
- S2.7-AC2 A background job submits public pages to Wayback Save Page Now within the documented limits, polls status and updates `sources.archive`; failures never block runs.
- S2.7-AC3 `archive.wayback_lookup` and `archive.wayback_cdx` tools with cassette contract tests.
- S2.7-AC4 The earliest-appearance function (03 §8.7) is property-tested; an archive capture counts as "existed no later than".

### S2.8 News, fact-check and reference sources (size L)
Refs: 04 §3.
- S2.8-AC1 GDELT DOC 2.0 adapter (phrases, language, date range, article list) storing sources with attribution.
- S2.8-AC2 Google Fact Check Tools adapter (`claims:search`) producing fact-check sources with publisher, rating text and review date.
- S2.8-AC3 RSS/Atom adapter (feedparser) that never raises on malformed feeds (fuzz property test).
- S2.8-AC4 Wikipedia and Wikidata adapters with a compliant User-Agent; a reliability rule marks them background-only, so they can never be the sole support for high confidence.

### S2.9 Playbooks v1 (size M)
Refs: 03 §3.
- S2.9-AC1 `verify_claim` and `reconstruct_event` validate and run end-to-end in replay mode, producing their report sections; `research` is refined.
- S2.9-AC2 Interactive plan review lets the user add, edit and remove questions before research starts.
- S2.9-AC3 The planner adds the languages of the places and subjects involved; an eval case shows non-English queries in `search_log`.
- S2.9-AC4 `lantern add-source <inv> --url <u> | --file <path>` captures evidence the user brings (a URL fetched through SafeTransport, or a file stored in the blob store), rated F until the user rates it with a reason, recorded as supplied by the user, and treated as untrusted content like any other source.

### S2.10 Evidence bundle (size M)
Refs: 02 §10.
- S2.10-AC1 `lantern export <inv> --bundle` writes a ZIP with `manifest.json` (sha256 per file), report (MD, HTML, JSON), sources and claims JSON, WARC files, the event chain and its verification result.
- S2.10-AC2 `lantern bundle verify <zip>` re-hashes every file and reports mismatches.
- S2.10-AC3 Optional RFC 3161 timestamp of the manifest hash from a configured time-stamping authority, stored in the bundle with verification instructions.

### S2.11 Evals v1 (size M)
Refs: 03 §12.
- S2.11-AC1 At least 10 cases across `research`, `verify_claim` and `reconstruct_event`, covering traps, injection canaries, independence, time ambiguity and non-English evidence.
- S2.11-AC2 Replay-mode evals run in CI; live mode runs with `make evals`; the baseline is updated through an approved PLAN; calibration (Brier score) is reported.

### S2.12 Retention and deletion (size M)
Refs: 02 §14; 07 §6.
- S2.12-AC1 `retention_until` is set at completion (default 180 days); `lantern hold <inv> --reason` sets a hold.
- S2.12-AC2 Deletion runs through a `SECURITY DEFINER` function owned by a maintenance role (the application role still cannot UPDATE or DELETE events): in one transaction it deletes the investigation's rows, event chain included, and appends a receipt to the system chain; the job then removes unreferenced blobs and WARC files, retrying failures; the system chain still verifies.
- S2.12-AC3 Source-specific retention limits from terms (for example a 30-day cache limit) are enforced by a refresh-or-delete job.

**M2 demo**: verify a real viral claim end-to-end with `verify_claim`; kill the worker mid-run and restart it; read the report's bottom line, likelihood and confidence wording, ACH appendix and removed statements; export and verify the evidence bundle.

---

## M3 — Workspace (web)

### S3.1 API v1 (size L)
- S3.1-AC1 FastAPI routes of 02 §16 with Pydantic models and an OpenAPI schema; bound to localhost only.
- S3.1-AC2 Server-sent events stream an investigation's events in order with resume from the last sequence number.
- S3.1-AC3 Source HTML is never served from the API origin; text views and downloads only (security test).

### S3.2 Web shell (size M)
- S3.2-AC1 Vite + React + TypeScript app with types generated from the OpenAPI schema; typecheck, unit tests (Vitest) and build pass in CI.
- S3.2-AC2 Investigations list and new-brief form (purpose, playbook, policy result, attestation).

### S3.3 Live run view (size M)
- S3.3-AC1 Questions board with live status, activity stream, spend meter and cancel.
- S3.3-AC2 Approval cards for plan review, premium tool calls and budget raises, with approve, deny and edit.
- S3.3-AC3 `make smoke` brings up the compose stack (database, worker, API serving the web build) and drives a replayed investigation through the HTTP API to a published report.

### S3.4 Report view (size M)
- S3.4-AC1 Rendered report with likelihood and confidence badges; citation cards show quote in context, source rating, origin and archive links.
- S3.4-AC2 Removed-statements and policy appendices are visible.

### S3.5 Evidence view and corrections (size M)
- S3.5-AC1 Sources table (rating and basis, origin cluster, archive status) and claims list.
- S3.5-AC2 Reject or restore a claim, override a rating with a reason, add a source by URL or file; each is an event and triggers recomputation.
- S3.5-AC3 Original HTML opens only in a sandboxed viewer on a separate origin with a restrictive CSP.

### S3.6 Timeline and ACH views (size M)
- S3.6-AC1 Timeline of dated claims showing precision and conflicts.
- S3.6-AC2 ACH matrix with diagnostic claims highlighted.

### S3.7 Exports and settings (size S)
- S3.7-AC1 Export buttons for MD, HTML, JSON and the evidence bundle.
- S3.7-AC2 Settings page shows which adapters are enabled, missing keys, model routing and budget defaults (no secret values).

**M3 demo**: run `verify_claim` entirely from the browser, approve a premium step, correct a claim, watch the finding update, export the bundle.

---

## M4 — Packs (epics; decompose each with `$plan-epic <ID>` when it is next)

A pack is done when: its adapters have cassette contract tests and verified rows in `04_DATA_SOURCES.md`; its playbook(s) run end-to-end in replay; policy rules cover its new subject types; at least 5 eval cases pass live; licence and attribution notes appear in reports.

| Epic | Scope | Notes |
|---|---|---|
| **P-EARTH** Earth observation | Scene search (Copernicus STAC), before/after image chips (Sentinel Hub Process API: Sentinel-1 radar, Sentinel-2 optical), change measured by code (radar backscatter drop for water, water index, burn index), NASA FIRMS fires, NASA GIBS daily tiles, GDACS disaster events, Copernicus EMS published maps, ReliefWeb reports (appname), rainfall history; imagery claims with date, sensor and method; map view of flooded or burnt areas; `area_change` playbook; `reconstruct_event` gains satellite and disaster steps | Satellite readings are evidence with stated uncertainty (cloud, resolution, revisit gaps), never ground truth. |
| **P-PEOPLE** People | `public_figure_profile` and `person_lookup` playbooks; candidate separation and attribution rules of 03 §8.8; anchors from personal sites, team pages, Wikidata and official sites; link-back checks through official APIs; purpose rules of 07 §2.1–§2.2; 30-day retention for person lookups; eval worlds with same-name people and planted wrong-person articles | `person_lookup` is never available to demo visitors. |
| **P-MEDIA** Media verification | Image and video ingest (sha256, perceptual hash), EXIF/XMP via exiftool with argument lists, C2PA check (`c2pa-python`), video keyframes (ffmpeg), near-duplicate search across preserved media, assisted reverse-image pivots (open Google Lens/Yandex/Bing/TinEye in the user's browser, paste results back), geolocation assistant (clues → candidates → constraints: Overpass, sun position, historical weather), chronolocation; `media_verify` playbook; evals with openly licensed images | No face recognition. Forensic signals are never verdicts. |
| **P-ORG** Organisations | GLEIF, UK Companies House, SEC EDGAR, official sanctions lists (OFAC, UN, EU), OpenSanctions (non-commercial or licensed), OpenCorporates (permitted-user tier), adverse-media queries; entity keys (LEI, company number + jurisdiction, CIK); `org_due_diligence` playbook | People appear only in their professional role. |
| **P-INFRA** Infrastructure | RDAP, DNS, certificate transparency (crt.sh), urlscan.io search, VirusTotal (non-commercial), Wayback history; relations such as resolves-to and shares-certificate; `domain_profile` playbook | Organisation and infrastructure level only. |
| **P-SOCIAL** Social | Bluesky (official API, user's own account for search), Mastodon (public timelines and hashtags), YouTube Data API, manual ingest for unsupported platforms; Reddit only after API approval; X content search only, approval-gated, if its terms permit the use; `self_audit` playbook | Terms re-checked at epic start (04 §4). |
| **P-MOVE** Movement | ADS-B (OpenSky for non-commercial research, adsb.lol archives, airplanes.live), aircraft registries, AIS (AISStream), NASA FIRMS; presence-near-event claims with coverage caveats; `movement_near_event` playbook | Licences differ per source; non-commercial flags. |
| **P-INDIA** Regional India | Indian fact-checkers via ClaimReview, curated RSS of Indian outlets in several languages, official press releases, multilingual query expansion and transliteration aliases; manual pivots for registries without APIs | Draws on M2 language support. |

Suggested order: P-EARTH → P-MEDIA → P-PEOPLE → P-MOVE → P-ORG → P-INFRA → P-SOCIAL → P-INDIA (events and verification first; they make the most striking demos). Reorder freely; packs are independent.

## M5 — Operate (epics)

| Epic | Scope |
|---|---|
| **O-DEMO** Public demo for recruiters | Oracle Cloud Always Free ARM VM (2 OCPU, 12 GB) running the compose stack behind Caddy with automatic HTTPS on a free subdomain; owner login (password + TOTP); visitor invite codes; demo mode rules of 07 §2.3 (playbook allow-list, code-checked public-role evidence for `public_figure_profile`, default caps of 3 live investigations per visitor code per day, 10 in total per day and US$1 per day on paid models, no trial-class models, 7-day retention for visitor investigations); a gallery of recorded investigations that replay instantly; a static showcase of published reports on GitHub Pages linked from the README; a deploy script and a written runbook, including keeping the VM above Oracle's idle-reclamation thresholds and what to do on "out of capacity" errors |
| **O-WATCH** Monitors | Scheduled delta runs, change detection (new sources, page changes, list changes), de-duplication, alerts to you (email, or a Telegram bot to your own chat), per-run budgets |
| **O-BACKUP** Backups | Nightly `pg_dump` plus a copy of the data folder to private cloud storage; a tested restore drill |
| **O-OBS** Observability | Cost, quota and quality dashboards from `llm_calls`, `llm_quota`, `tool_calls` and eval results |

### Not planned

Commercial use and paid customers · commercial-mode licence switches (04 §11) · multiple full user accounts and teams · privacy notice, data-processing records and data-subject requests for customers (07 §11). Any of these needs a decision record first.
