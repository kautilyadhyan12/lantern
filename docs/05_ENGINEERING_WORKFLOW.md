# 05 — Engineering Workflow

Pack 3.0 · written 2026-10-22 · status: source of truth for how work gets done

The coding agent is **Codex** (OpenAI's coding agent, signed in with your ChatGPT plan), working inside a **GitHub Codespace**. You are a beginner: the agent does the work and the housekeeping, and stops at fixed points for your yes.

## 0. Principles

1. **The verifier must be something the implementer cannot influence.** Three such verifiers exist here: the machine (types, tests, CI on GitHub), an independent fresh reviewer session that sees only artefacts (T3), and reality (recorded real responses, live evals, the running product).
2. **Enforce with tools, not with prose.** `AGENTS.md` is guidance; command rules, hooks and CI are enforcement. Anything that must never happen is a rule, a hook or a failing check.
3. **Spend effort where defects hide.** Product risk lives in analysis quality, egress safety and policy. Process machinery is kept small.
4. **You decide; the machine proves.** You approve the next story, each PLAN, CI and harness changes, and every merge to `main`. Everything that can be checked mechanically is checked mechanically.

## 1. The loop

```
pick         the agent names the next story and why                        → WAIT for your yes
$plan        docs/plans/PLAN-<ID>.md + plain-English summary in chat         → WAIT for your yes
$tests-first failing tests for every AC; RED run logged in the PLAN          → report
$implement   smallest code that turns the tests green; make check green      → report
$prove       commit; make prove STORY=<ID> → docs/proofs/PROOF-<ID>.md       → report
$review      make review STORY=<ID>: a fresh reviewer session in a throwaway
             copy of the repo → docs/reviews/REVIEW-<ID>.json; triage        → report
fix          REQUEST_CHANGES: fix → $prove → $review again (max 3 rounds)
             APPROVE: commit the reviewer's tests → $prove on that commit
$ship        push → PR → CI green → ASK you → squash-merge → clean up
$smoke       run the smoke check on main (when the milestone has one)        → report
```

Rules:
- One story per branch (`story/<ID>`), one story per Codex session. Start each story in a new session.
- Each step finishes and is reported before the next starts. Nothing is skipped or reordered.
- If a step needs a tool that a later story builds, stop and ask — unless the skill says exactly what to do.
- Never commit to `main` directly; never merge without your yes.
- A story's diff is at most ~400 non-test lines; larger stories are split in `$plan`, with your approval. The user approved a one-story exception of up to 800 handwritten non-test lines for S0.2 in [ADR 0003](adr/ADR-0003-proof-kit-size-and-strict-audit.md); its quality, proof and review gates remain required.

### 1.1 Housekeeping the agent always does

- **Save and back up.** At the end of every step: commit on the story branch and push it (`git push -u origin HEAD`). Work is then safe on GitHub even if the codespace is deleted.
- **Tell you when you can stop.** At the end of a session: "Everything is saved and pushed. You can close this tab." GitHub stops a codespace after 30 minutes without activity and deletes stopped codespaces after 30 days (account defaults), so nothing else is needed.
- **Watch the free hours.** If you mention the codespace felt slow or you are near the monthly limit, the agent reminds you where to check usage (GitHub → Settings → Billing). It never changes your account settings.
- **Keep secrets out.** API keys live in Codespaces secrets (environment variables). `.env` files are never committed.

## 2. Definition of done

A story is done when all of these hold:

1. The PLAN was approved by you.
2. Every AC has at least one test marked `@pytest.mark.ac("<ID>")`, and the RED run (tests failing for the right reason before implementation) is logged in the PLAN.
3. `docs/reviews/REVIEW-<ID>.json` says `APPROVE` for the reviewed commit. The branch's final commit differs from the reviewed commit only by the reviewer's new files under `tests/review/` and by files under `docs/`.
4. `docs/proofs/PROOF-<ID>.md` was produced on that final commit's code and ends `RESULT: PASS`.
5. CI is green on the PR, including the review-artifacts check (from S0.5 on).
6. Design changes are recorded (a decision record in `docs/adr/` and the affected doc updated).
7. The PR is squash-merged and the branch deleted.

Quality bar (`make check`; never lowered without a recorded decision):

| Check | Threshold |
|---|---|
| ruff check, ruff format | clean |
| `scripts/lint_custom.py` | clean (no broad excepts that swallow errors; `type: ignore` and `noqa` only with a stated reason; skip/xfail only with an issue link; no `time.sleep`/`print` in `src/`; no `shell=True`) |
| dependency deny-list (`scripts/check_dependencies.py`) | no face-recognition or face-embedding libraries in `uv.lock` |
| import contracts (`lint-imports`) | clean (layers of 02 §5) |
| mypy `--strict` | clean |
| tests | all pass; no new skip/xfail without an issue link |
| coverage | total ≥ 85%; each critical path ≥ 95% |
| bandit, pip-audit | clean |
| evals (from S1.13 on, when prompts, routing, roles, assessment rules or the loop change) | no pass→fail; mean judge drop ≤ 2 |

### 2.1 Tooling configuration (installed by S0.1)

`pyproject.toml` essentials (S0.2 adds `[tool.lantern.quality]` and the import contracts):

```toml
[project]
name = "lantern"
requires-python = ">=3.12"

[project.scripts]
lantern = "lantern.cli:main"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E","F","W","I","N","UP","B","A","C4","DTZ","T10","EM","ISC","PIE","PT","RET","SIM","TID","ARG","PL","RUF","S","BLE","TRY","ASYNC"]
ignore = ["PLR2004","TRY003","EM101","EM102"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101","PLR","ARG"]
"tests/review/**" = ["S101","PLR","ARG","N999"]

[tool.mypy]
strict = true
warn_unreachable = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers -p no:cacheprovider --import-mode=importlib"
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
  "ac(id): acceptance criterion id",
  "review: adversarial test written by the independent reviewer",
  "live: calls real external APIs",
  "slow: slow test",
]

[tool.coverage.run]
branch = true
source = ["src/lantern", "scripts"]
```

`scripts/lint_custom.py` forbids, with one rule ID each:
- `except Exception`, `except BaseException` or bare `except` whose handler neither re-raises nor logs with `.exception(...)`;
- `# type: ignore` or `# noqa` without a trailing reason comment;
- `pytest.skip`, `skipif`, `xfail` or `importorskip` without an issue URL;
- `time.sleep` in `src/`;
- any call with `shell=` set to anything other than literal `False`;
- `print(` in `src/`.

## 3. Codex setup (committed with the pack)

Everything is committed to the public repository: `AGENTS.md`, `.agents/skills/`, `.codex/` and `docs/`. Lantern is openly built with an AI coding agent under a strict, tested workflow; that is part of what the project demonstrates.

Codex loads the project's `.codex/` folder (settings, rules, hooks) only after you **trust the project** the first time you start Codex in it (`08_SETUP.md` §4). Hooks also ask to be trusted once (`/hooks`).

### 3.1 `.codex/config.toml`

```toml
model = "gpt-6.1-sol"
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = true
```

- `gpt-6.1-sol` is the recommended Codex model on ChatGPT plans; switch with `/model` if your plan's limits run out.
- `workspace-write` lets the agent edit files in the repository and run commands; `on-request` makes it ask before anything outside that. Network access is on because installing packages, pushing branches and calling APIs need it.
- If the sandbox cannot start inside the codespace (sandbox errors on every command), the agent stops and asks. A codespace is already an isolated cloud machine, so switching that one session to `sandbox_mode = "danger-full-access"` is acceptable there; the rules and hooks below still apply.

### 3.2 Command rules (`.codex/rules/default.rules`)

Shipped with the pack. Prefix rules: `forbidden` blocks a command; `prompt` asks you first. Never use `allow` here (in Codex it means "run outside the sandbox without asking").

| Pattern (prefix) | Decision | Why |
|---|---|---|
| `git push --force` · `git push -f` · `git push --force-with-lease` | forbidden | rewrites history |
| `git reset --hard` · `git clean` | forbidden | destroys work |
| `git filter-branch` · `git reflog expire` | forbidden | rewrites history |
| `rm -rf` | forbidden | destroys files |
| `pip install` · `uv pip` · `python -m pip` | forbidden | dependencies only via `uv add` |
| `git push origin main` · `git push origin HEAD:main` | forbidden | `main` changes only through a merged PR |
| `gh pr merge` | prompt | merging needs your yes |
| `gh api` · `gh repo` · `gh secret` | prompt | account-level actions |

Prefix rules only match the start of a command. The S0.3 hook (`guard_shell`) catches the other spellings (`git -C . push --force`, `cd x && rm -rf y`, writing into protected folders with `>`). S0.3 checks every rule with `codex execpolicy check`.

### 3.3 Hooks (added by S0.3)

- `PreToolUse` → `scripts/hooks/guard_shell.py`: blocks the commands of S0.3-AC1 in any spelling, and blocks file edits to `tests/fixtures/`, `docs/proofs/`, `docs/reviews/`, `.codex/` and `.github/`.
- `PostToolUse` → `scripts/hooks/post_edit.py`: formats and lint-fixes an edited Python file and feeds remaining problems back.

When a story itself must change `.codex/` or `.github/` (S0.3, S0.5, later harness changes), the agent asks you to restart Codex with `LANTERN_ALLOW_HARNESS_EDITS=1 codex` for that session. The hook reads that variable from Codex's own environment, which the agent cannot change.

The exact hook file format and payload fields are taken from the installed Codex version in S0.3 (a real payload sample goes into the PLAN). Hooks match all tools (`matcher: ".*"`); the scripts look at the payload and ignore tools they do not guard.

### 3.4 Skills (`.agents/skills/<name>/SKILL.md`)

Invoke a skill by typing `$` and its name, followed by the story ID, for example `$plan S0.1`. `/skills` lists them.

| Skill | Does |
|---|---|
| `$plan` | reads the story and design sections; re-checks external facts; writes the PLAN; posts a plain-English summary; stops |
| `$plan-epic` | turns an M4/M5 epic into stories with ACs; proposes; adds them to the backlog only after your yes |
| `$tests-first` | writes failing tests per AC; runs them; logs the RED run; stops |
| `$implement` | writes the smallest code to pass; runs `make check`; optional advisory audits; stops |
| `$prove` | commits; runs `make prove STORY=<ID>`; reports the PROOF summary |
| `$review` | runs the independent review in a fresh session; triages the verdict |
| `$ship` | pushes, opens the PR, waits for CI, asks you, merges, cleans up |
| `$smoke` | runs the milestone's smoke check on `main` |
| `$security-audit` · `$test-audit` | advisory read-only checklists the implementer may run before `$prove`; they never replace the review |

## 4. T3 review prompt

The fenced block below is the exact content of `.codex/prompts/t3.md` (a test compares them). `{STORY}`, `{STORY_SLUG}` (the ID in lower case with dots replaced by underscores, e.g. `s1_3`), `{ROUND}` (1 for a story's first review, then 2, 3) and `{BASE}` (default `main`) are substituted before use. The file is the block followed by one newline.

```
You are T3, an independent reviewer with no prior context on this work. You did not write it. Assume it is wrong until the evidence shows otherwise. A finding counts only if it is backed by (a) a failing test you wrote and ran, or (b) a verbatim quote from the PLAN, the backlog or a design document that the change contradicts. Anything else is a note and cannot block.

Story: {STORY}
Diff base: {BASE}
Review round: {ROUND}

You may read: docs/plans/PLAN-{STORY}.md, docs/proofs/PROOF-{STORY}.md, docs/06_ROADMAP_BACKLOG.md, the other docs/0*.md files, AGENTS.md, the diff (git diff {BASE}...HEAD) and any file in the repository.
You may run: git diff, git log, git show, git rev-parse, git status, uv run pytest, uv run ruff, uv run mypy.
You may create new files only under tests/review/. Do not modify, fix, refactor or reformat any existing file. You are reviewing, not repairing: describe needed changes in your findings. You are working in a throwaway copy of the repository; only your new file under tests/review/ is kept.

Do every step below. Do not stop early.

1. SCOPE. List the changed files. Flag any change outside the PLAN's scope: a blocker if it changes behaviour, otherwise a note.
2. SPEC CONFORMANCE. For each acceptance-criterion ID in the PLAN, find the tests marked @pytest.mark.ac("<ID>") and the code that implements it. Mark it SATISFIED, PARTIAL or MISSING with file:line evidence. PARTIAL or MISSING is a blocker.
3. PROOF INTEGRITY. Read the commit SHA recorded in the PROOF and run git diff --name-only <that SHA> HEAD: HEAD may differ from it only in files under docs/. Every step must show exit code 0 and the final line must be RESULT: PASS. Thresholds must meet AGENTS.md. Any mismatch is a blocker.
4. ADVERSARIAL TESTS. Write at least six tests in a new file tests/review/test_{STORY_SLUG}_r{ROUND}_adversarial.py. Files from earlier rounds are regression tests: run them, never edit them. Attack whatever applies: boundaries; empty, None and oversized inputs; Unicode, right-to-left and mixed-script text; naive versus timezone-aware datetimes and timezone edges; malformed or partial external payloads; network failures (429, 5xx, timeouts); budget exhaustion mid-step; repeated or concurrent execution (idempotency); security (SSRF targets, path traversal, injection, instructions hidden in captured content). Mark each test @pytest.mark.ac("<ID>") when it targets an acceptance criterion, otherwise @pytest.mark.review. Run them. Every failing test is a blocker; include its failure output.
5. INDEPENDENT REFERENCE. For each pure function named in the PLAN's design section (parsers, normalisers, rule tables, scoring), write your own reference implementation from the PLAN's description before reading the implementation, and compare the two on hypothesis-generated inputs. A disagreement is a blocker, unless the PLAN is ambiguous: then record a spec ambiguity.
If tests that need the local database fail only because it cannot be reached from your sandbox, record that as a note, not a blocker.
6. TEST QUALITY. Find vacuous tests: assertions on mocks only, tautologies, duplicates, tests that cannot fail. Changed behaviour without a meaningful assertion is a blocker.
7. INVARIANTS AND SECURITY. Check the change against the non-negotiable invariants in AGENTS.md, and for secrets in code or logs, personal data in logs, unsafe subprocess use, unsafe file paths, and unbounded loops or spend. A violation is a blocker.
8. NOTES. Maintainability and design observations, as notes.

Final output: print exactly one JSON object and nothing else:
{
  "story": "{STORY}",
  "reviewer_model": "<your model id>",
  "head_sha": "<output of git rev-parse HEAD>",
  "verdict": "APPROVE or REQUEST_CHANGES",
  "ac_status": [{"ac_id": "...", "status": "SATISFIED|PARTIAL|MISSING", "evidence": "file:line ..."}],
  "blockers": [{"id": "B1", "kind": "scope|spec|proof|test|security|reference", "evidence": "...", "fix_hint": "..."}],
  "spec_ambiguities": [{"ac_id": "...", "question": "..."}],
  "notes": ["..."],
  "adversarial_tests_file": "tests/review/test_{STORY_SLUG}_r{ROUND}_adversarial.py",
  "adversarial_results": {"passed": 0, "failed": 0}
}
The verdict must be REQUEST_CHANGES if blockers is non-empty or any adversarial test failed.
```

### 4.1 How the review runs

`make review STORY=<ID>` (built in S0.4; before that the agent performs the same steps by hand, §4.2):

1. Refuse if the working tree is dirty.
2. Create a throwaway git worktree of HEAD outside the repository and run `uv sync --frozen` in it.
3. Substitute the placeholders in `.codex/prompts/t3.md`.
4. Start a **fresh** Codex session in that worktree (§4.2). It shares nothing with the implementer's session.
5. Validate the reviewer's final JSON against `scripts/review_schema.json`; check `head_sha` equals the HEAD that was reviewed.
6. Add `code_tree` (the code-tree hash excluding `docs/` and `tests/review/`, from `scripts/code_tree.py`) and write `docs/reviews/REVIEW-<ID>.json`; copy back only the reviewer's new file under `tests/review/`.
7. List anything else the reviewer changed (discarded with the worktree) in the REVIEW notes; delete the worktree.

The agent may run `make review` itself: independence comes from the fresh session, a different model and the throwaway copy, not from who presses the button. The agent may never edit the prompt, the REVIEW file, or `scripts/review.py` outside a story whose PLAN you approved for that purpose.

### 4.2 The reviewer command

```
codex exec \
  --cd <worktree> \
  --sandbox workspace-write \
  --model gpt-6-astra \
  --ephemeral \
  -c approval_policy="never" \
  --output-schema scripts/review_schema.json \
  --output-last-message <file> \
  "<prompt with placeholders substituted>"
```

- **Fresh session**: `codex exec` starts a new session; `--ephemeral` keeps it from being saved for later resumption.
- **Different model**: the reviewer uses `gpt-6-astra` (the most capable Codex model), the implementer `gpt-6.1-sol`. If your plan's limits for `gpt-6-astra` are used up, `LANTERN_REVIEW_MODEL=gpt-6-sol` switches it.
- **Throwaway copy**: the reviewer may write anywhere in the worktree, but only its new `tests/review/` file survives.
- **No network by default** inside the review sandbox, so captured content or test code cannot send anything out. If the e2e tests need the local database, S0.4 decides how to allow only that.
- `scripts/review_schema.json` ships with the pack, so the schema exists from the start.
- `make review` writes the reviewer's output to a temporary file and then to `docs/reviews/REVIEW-<ID>.json` after validation. Before S0.4 exists (the M0 bootstrap, S0.3 and S0.4 itself), the agent runs these steps by hand, shows you each command first, and passes `--output-last-message docs/reviews/REVIEW-<ID>.json` directly: that `codex exec` command is the only sanctioned by-hand writer of REVIEW files.
- For those manual bootstrap reviews, [ADR 0004](adr/ADR-0004-bootstrap-review-metadata.md) resolves the shipped schema's missing `code_tree` field: use a temporary output schema outside the repository with that one required field fixed to the independently computed digest. Validate the output minus that field against the unchanged shipped schema, and validate its digest and reviewed HEAD separately. The reviewer CLI remains the sole artifact writer; never repair or rewrite its output.
- The worktree is a different folder, so Codex does not load the project's rules or hooks there; the sandbox and the throwaway copy are what contain the reviewer. Check the flags against `codex exec --help` in S0.4; they change between versions.

### 4.3 After the review

1. The agent reads the REVIEW file and reports the verdict and blockers in plain English.
2. The reviewer's test file is committed (`<ID>: add review tests, round <N>`). It stays forever as a regression suite; it is edited only to remove a genuine test bug, logged in the PLAN. Each round writes a new file, so earlier rounds are never overwritten.
3. **REQUEST_CHANGES**: fix the blockers, then `$prove` and `$review` again. **APPROVE**: `$prove` once more on the commit with the review tests, then `$ship`.
4. After 3 rounds without APPROVE: stop and propose a split via `$plan`.

## 5. Tests

| Folder | What | Runs in |
|---|---|---|
| `tests/unit/` | pure logic, no I/O | `make check`, CI |
| `tests/property/` | hypothesis properties for every pure function (normalisers, parsers, rule tables, scoring, budget arithmetic, IP classes) | `make check`, CI |
| `tests/contract/` | each adapter against recorded cassettes, including error cases (429, 5xx, malformed) | `make check`, CI |
| `tests/e2e/` | database-backed flows and whole investigations replayed from cassettes | `make check`, CI |
| `tests/review/` | T3's adversarial tests, kept forever | `make check`, CI |
| `tests/live/` | real APIs, tiny quotas, schema drift checks (marker `live`) | `make live`, manual or weekly |

### 5.1 Coverage

Measured over `src/lantern` and `scripts`. Total ≥ 85%. Each **critical path** ≥ 95%: `src/lantern/core`, `src/lantern/policy`, `src/lantern/egress`, `src/lantern/db/events.py`, `src/lantern/tools/gateway.py`, `src/lantern/llm/gateway.py`, `src/lantern/report/render_html.py`, `scripts/hooks`. Paths that do not exist yet are reported, not failed.

### 5.2 Mutation testing

Optional, not a gate: `make mutate` (works in Codespaces) on `core`, `policy` and `egress` before closing a milestone; surviving mutants are reviewed and either killed with a test or explained in the PLAN.

## 6. Recordings, eval worlds and prompts

**HTTP and model cassettes** (`tests/fixtures/cassettes/`):
- Created only by `scripts/record_fixture.py`, which makes real calls with keys from the environment (Codespaces secrets) and sanitises secrets: `tool <tool> <case> --args <json>` records one tool call; `pytest <test ids>` runs those tests in record mode and records only the cassettes they are missing (HTTP, and model cassettes from S1.8 on — this is how model and golden-run cassettes are made); `--refresh` re-records existing ones. Never written by hand (the S0.3 guard enforces this).
- Each file starts with a provenance header (recorder, time, tool, tool version, request fingerprint). `scripts/check_fixture_signatures.py` rejects files without it, with a stale tool version, or containing secret-like values.
- A replay miss fails loudly; replay never falls through to the network.
- Cassettes are recorded once the adapter code can make the call, in `$implement`, with your approval. During `$tests-first`, contract tests may be RED with `CassetteMiss`; that is a valid RED reason.
- Search-API cassettes are kept minimal (a few small responses for parser tests), because providers restrict storing results.
- An adapter version bump requires re-recording its cassettes in the same story.

**Eval worlds** (`evals/worlds/`): authored scenarios, not recordings. They use fictional people and organisations, are reviewed in the PLAN of the story that adds them, and are labelled synthetic in `world.yaml`.

**Prompts** (`src/lantern/llm/prompts/`): a change means a new version file, re-recorded model cassettes for affected tests, and — from S1.13 on — a live eval run on the affected cases whose summary (scores, tokens, cost, regressions) is pasted into the PLAN. Live evals use free quota, so run a few cases at a time. The user approves any accepted regression.

## 7. The PLAN file

```
# PLAN <ID> — <title>
## Goal                       one paragraph, plain English
## Scope                      in / out
## Design                     interfaces with full signatures; data and migrations; files touched
## Acceptance criteria        verbatim from the backlog; a "Proposed AC changes" subsection only with the user's approval
## Test plan                  per AC: file, test names, kind; cassettes to record; eval cases
## External facts checked     what was verified today, with URLs (or "none")
## Risks and mitigations      security, privacy, platform terms, cost
## Size                       non-test LOC estimate; split proposal if above 400
## Rollback
## Log                        append-only: RED run, decisions, deviations, review rounds, proof results
```

## 8. Continuous integration

### 8.1 `.github/workflows/ci.yml`

Template — S0.5 pins every action to a full commit SHA (resolved at build time) and the user approves the file.

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 40
    services:
      db:
        image: pgvector/pgvector:0.8.6-pg16
        env:
          POSTGRES_USER: lantern
          POSTGRES_PASSWORD: lantern-ci
          POSTGRES_DB: lantern
        ports: ["5434:5432"]
        options: >-
          --health-cmd "pg_isready -U lantern"
          --health-interval 5s --health-timeout 5s --health-retries 20
    env:
      LANTERN_DATABASE_URL: postgresql+asyncpg://lantern:lantern-ci@localhost:5434/lantern
    steps:
      - uses: actions/checkout@<pinned-sha>      # vN
      - uses: astral-sh/setup-uv@<pinned-sha>    # vN
        with:
          enable-cache: true
      - run: uv sync --frozen
      - run: make check
      - run: uv run python scripts/check_review_artifacts.py --pr-title "$PR_TITLE"
        if: github.event_name == 'pull_request'
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}
  actionlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<pinned-sha>      # vN
      - uses: raven-actions/actionlint@<pinned-sha>   # or the official actionlint runner; choose in S0.5
```

From M2, a third job runs replay-mode evals. CI never needs secrets until live checks are scheduled (optional, later).

### 8.2 Pull-request template (`.github/pull_request_template.md`)

Story ID and title · Summary · AC → tests table · Risks · Rollback · Checklist: `make check` green; PROOF and REVIEW for this code (CI checks them); no fixtures, proofs or reviews edited by hand; docs and decision records updated if the design changed.

### 8.3 Branch protection on `main` (set by the user in GitHub settings)

Require a pull request before merging (0 approvals — solo developer); require status checks `check` and `actionlint`; require branches to be up to date; require linear history; block force pushes; block deletions.

## 9. Git conventions

- The repository is **public**. Never commit secrets, `.env` files, personal data, or captured evidence (`var/` is ignored).
- Branch `story/<ID>`; commits `<ID>: <imperative summary>`; squash-merge with the PR title `<ID>: <title>`.
- Codex may add its own co-author line to commits; that is fine and honest.
- `docs/` (plans, proofs, reviews, decisions) is committed: it is the project's memory and part of the showcase.

## 10. Commands

| Command | Does |
|---|---|
| `uv sync` | install locked dependencies |
| `make db` / `make db-down` | start / stop the local Postgres |
| `make hooks` | install pre-commit hooks |
| `make check` | the full local gate (§2) |
| `make prove STORY=<ID>` | run the gate on a clean tree and write the PROOF |
| `make review STORY=<ID>` | run the independent review (§4) |
| `make evals` | live evals (M1+, uses free model quota) |
| `make live` | real-API drift checks (adapter stories onward) |
| `make smoke` | milestone smoke check (M1+) |
| `make mutate` | optional mutation testing; add the target the first time it is wanted |
| `uv run python scripts/record_fixture.py tool <tool> <case> --args <json>` · `… pytest <test ids>` | record one call · record what those tests are missing (HTTP and model) |

## 11. Escalation

- Three review rounds without APPROVE → split the story via `$plan`.
- A spec ambiguity → stop and ask you; record the answer in the PLAN (and the backlog if an AC changes).
- External API drift found by `make live` → a `FIX-<tool>` story with fresh cassettes; never a silent patch.
- A gate that cannot run yet → stop and ask.
- Codex usage limits reached → say so plainly; continue later or switch model with `/model`.

## 12. Session hygiene

- Start each story in a new Codex session (exit with `/quit` or close the terminal, then run `codex` again) and begin with `$plan <ID>`, or the next step if the PLAN exists.
- After a long session or a context compaction, re-read `AGENTS.md`, the PLAN and the latest PROOF/REVIEW before continuing.
- Commit and push at the end of every step (§1.1).
