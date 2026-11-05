# 09 — Decision Log

Pack 3.0 · written 2026-10-22

Accepted additions: [ADR 0001 — Official Node.js security updates bypass the cooldown](adr/ADR-0001-node-security-update-cooldown.md) clarifies the development supply-chain policy. The seven-day wait remains for everything else.

[ADR 0002 — Use checked security fixes without an age delay](adr/ADR-0002-advisory-checked-security-updates.md), accepted 2026-10-23, supersedes that waiting period. Current advisory checks, official sources, locked versions/hashes and the other security rules remain required.

The decisions behind this pack, with what was rejected and why. Future changes go into `docs/adr/` as new records that cite the decision they change; the docs are then updated to match.

[ADR 0004 — Bind bootstrap reviews to code without editing generated artifacts](adr/ADR-0004-bootstrap-review-metadata.md), accepted 2026-10-26 with PLAN-M0, clarifies the pre-S0.4 manual reviewer output procedure without changing the shipped prompt or schema.

### D1 — Fresh start on a proven stack
**Decision.** Build from an empty folder. Keep Lantern's purpose (evidence-based OSINT), its non-negotiable ethics, and a mainstream stack: Python 3.12, uv, ruff, mypy strict, pytest/hypothesis, Pydantic, Postgres 16 + pgvector, SQLAlchemy async + Alembic, Docker Compose, the `openai` SDK against OpenAI-compatible providers.
**Why.** The earlier code was built for a different, heavier plan; starting clean avoids carrying its machinery. The stack is well supported, runs in Codespaces and CI alike, and is what AI coding agents handle best.
**Consequences.** M0 begins with the repository skeleton; S0.1 and S0.2 are built together as a one-time bootstrap (`08_SETUP.md` §5).

### D2 — Risk-first roadmap: the engine before breadth
**Decision.** M1 is a walking skeleton — the thinnest end-to-end investigation — followed by the trustworthy core (M2), the web workspace (M3), then vertical packs (M4).
**Why.** The biggest risk is whether the agent produces correct, well-calibrated, well-cited analysis. The previous plan spent ten infrastructure stories and some forty data-source integrations before any end-to-end run could show that. Evals from M1 measure quality while it is still cheap to change course.
**Rejected.** Breadth-first source catalogue; UI-first.

### D3 — Investigations are organised around key questions
**Decision.** The planner turns a brief into 3–10 key questions with answer criteria; research, assessment and reporting work per question. Playbooks become templates (seed questions, tools, limits, report outline), not step graphs.
**Why.** It is how analysts work; it gives measurable progress, natural stop conditions and precise eval targets; it adapts to what is found instead of following a fixed script.
**Rejected.** YAML step graphs (rigid, many execution features to build and test); a free-roaming agent (unbounded cost, untestable).

### D4 — Assessment standard: Admiralty ratings, ICD 203 likelihood, rule-based confidence
**Decision.** Sources keep Admiralty A–F, claims 1–6. Findings carry an ICD 203 likelihood term proposed by the model and an analytic confidence computed by code from the evidence profile; code clamps the likelihood so extreme terms need high confidence; likelihood and confidence are written in separate sentences.
**Why.** These are the professional standards investigators and editors recognise; they are explainable ("high confidence: three independent origins, one primary record"). The previous numeric prior table with noisy-OR produced precise-looking numbers with no calibration behind them.
**Rejected.** Numeric probabilities as outputs; model-only confidence.

### D5 — Record versus content, and independence by origin
**Decision.** A source supports *record* claims (it exists, who published it, when) separately from *content* claims (what it says). Corroboration counts independent origins: copies, syndication and repeated attribution to the same speaker count once.
**Why.** Verification work depends on both distinctions; the classic failure is many outlets repeating one unverified post.

### D6 — Short refs in everything the model reads and writes
**Decision.** `Q3`, `S12`, `C47`, `F2` instead of UUIDs.
**Why.** Fewer tokens, far fewer copying errors, every ref validated mechanically.

### D7 — Open-weight models through OpenAI-compatible APIs; structured output everywhere; no agent framework
**Decision.** The product calls models through one gateway using the `openai` SDK against OpenAI-compatible providers: free tiers (Groq, Cerebras, OpenRouter free models) by default, NVIDIA's trial endpoints for development only, DeepSeek's low-cost API as an option, local servers later. Every role, including the researcher's actions, returns one JSON object validated by Pydantic, using the strongest output control each provider supports. Steps are single-turn and stateless. Quotes are verified by code.
**Why.** Zero or near-zero cost, no lock-in to one vendor, and a design whose correctness comes from code checks rather than from a particular model — which is exactly what makes it trustworthy with weaker free models.
**Rejected.** A single paid vendor SDK; provider-specific function calling as the only action mechanism; LangChain/LangGraph-style frameworks; long multi-turn agent conversations.

### D8 — Durable runs with DBOS Transact, decided by a spike
**Decision.** Use DBOS Transact (Postgres-backed library, MIT) for workflows, durable approval waits and queues, behind a thin binding. S2.1 starts with a spike in the codespace and in CI; if it fails, use a small memoised-step runner on our own tables.
**Why.** Crash-safe resumption without repeating paid calls, and hours-long approval waits, are hard to build correctly; DBOS needs no extra server. Its 3.0 release (Sep 2026) changed APIs, hence the spike.
**Rejected.** Temporal (another server); hand-written DAG executor plus queue as the default.

### D9 — One SSRF-safe egress transport and URL provenance
**Decision.** All HTTP goes through one transport that validates every resolved address, pins connections, re-checks redirects and caps size and time. The fetch tool only accepts URLs already known to the investigation.
**Why.** One audited choke point beats per-adapter care. URL provenance stops prompt-injected exfiltration and hallucinated URLs.

### D10 — Search results are transient; evidence is what Lantern fetches
**Decision.** Search hits are used within the step that requested them and never stored; only the query, count and URL hashes are logged. Pages are fetched first-hand and preserved.
**Why.** Current search-API terms (Brave, Exa) forbid storing results, and a snippet is weak evidence anyway.

### D11 — Evidence preservation in standard formats
**Decision.** Content-addressed blobs; WARC records for HTTP captures; an evidence bundle with a hash manifest; optional RFC 3161 timestamp; Wayback submissions as a background job.
**Why.** Journalists and analysts need evidence that survives deletion and can be shown to be unaltered, in formats other tools can open.

### D12 — A lean workflow that keeps the strong gates
**Decision.** Keep: plan → tests-first → implement → prove → fresh-session review (T3) → fix → ship → smoke; ask-first rules; AC tracing; PROOF files; adversarial review tests kept forever; guards; recordings that cannot be hand-edited. Enforce with Codex command rules, hooks and CI (including a CI check that PROOF and REVIEW match the PR's code). The review runs as a fresh `codex exec` session, on a different model, in a throwaway worktree; the implementer may start it, because independence comes from the fresh session and the discarded copy, not from who starts it. Drop: a Stop-hook proof gate, proof stamps, signed fixtures, materialised review tests, plan linting, related-test mapping, mutation testing as a gate.
**Why.** An earlier attempt at this project spent five weeks on one and a half foundation stories, mostly hardening machinery that polices the agent. The kept gates catch the failures that matter; the dropped ones cost more than they caught. A beginner cannot run review sessions by hand reliably, so the review must be one command.

### D13 — Model routing by tier, in configuration
**Decision.** Roles map to tiers (`fast`, `standard`, `strong`); tiers map to ordered fallback lists of `provider:model` entries in `src/lantern/data/models.yaml`, with limits, prices and capabilities. Quotas are tracked per provider per day.
**Why.** Free tiers change often and run out daily; routing changes must be a configuration edit validated by evals, never a code change.

### D14 — Eval worlds make live evals possible
**Decision.** Live-model evals run against synthetic closed worlds (BM25 search over authored documents, fetch by URL, recorded structured responses) with planted traps, injection canaries and ground truth; replay evals run in CI.
**Why.** Exact-request cassettes break as soon as a prompt changes the model's queries; a closed world answers any query deterministically.

### D15 — Command line and HTML report before the web app
**Decision.** M1–M2 are CLI-driven with a self-contained HTML report; the web workspace is M3.
**Why.** The report is the product's core artefact; a UI before the engine is proven would be rebuilt.

### D16 — Module boundaries enforced by import contracts
**Decision.** `import-linter` layer contracts in `make check`; `core` and `policy` stay pure.
**Why.** An AI implementer optimises locally; contracts keep the architecture intact without a human reviewer.

### D17 — Bounded retention, real deletion, per-investigation hash chains
**Decision.** Default retention 180 days after completion, holds with reasons, source-specific limits; one event chain per investigation; deletion receipts on a system chain.
**Why.** Privacy law requires bounded retention; per-investigation chains make deletion compatible with tamper evidence.

### D18 — Public repository; built openly with an AI coding agent
**Decision.** The repository is public and contains everything: code, `docs/` (plans, proofs, reviews, decisions), `AGENTS.md`, `.agents/skills/`, `.codex/` and the dev container. Commits may carry Codex's co-author line. CI and harness files change only with the user's approval.
**Why.** For a portfolio, the design docs, proofs and reviews show how the project was engineered; hiding the AI agent would also hide the rigorous process around it. Supersedes the earlier local-only rule.

### D19 — Social sources follow current platform terms
**Decision.** Bluesky (user's own account), Mastodon and YouTube are in scope; Reddit only with written approval; X only for content search and only if its terms allow the use; Telegram, Threads, TikTok, Instagram, Facebook and LinkedIn only through manual ingest.
**Why.** Terms checked on 2026-10-17 restrict automated collection and "investigating or tracking" users; building against them risks bans and legal claims.

### D20 — A personal project with a public demo
**Decision.** Lantern is built for one owner and is non-commercial. A public demo (M5, O-DEMO) lets recruiters replay recorded investigations and run a few limited live ones under an invite code, a playbook allow-list and daily caps. No paid customers, teams or commercial licences.
**Why.** That is the real goal: a strong, demonstrable portfolio project at near-zero cost. Non-commercial data sources can be used within their own wording (`04` §11).
**Consequences.** The ethics invariants, purpose gate and data-protection engineering stay exactly as they are; demo visitors get a narrower product (`07` §2.3). The code still records each source's `commercial_ok`.

### D21 — Codex in GitHub Codespaces
**Decision.** The coding agent is Codex (signed in with the user's ChatGPT plan), working in a GitHub Codespace defined by a committed dev container. The agent does the housekeeping: commits and pushes every step, tells the user when they can close the tab; GitHub's defaults stop idle codespaces after 30 minutes and delete stopped ones after 30 days.
**Why.** The user's laptop has 4 GB of RAM, too little for Docker, Postgres, an editor and an agent together; a codespace has 8 GB and costs nothing within 60 hours a month. The user is a beginner, so manual housekeeping would be a source of lost work.
**Rejected.** Native Windows development on the 4 GB laptop; Claude Code (not available for this project).

### D22 — People: public figures fully, ordinary people only through a bounded professional lookup
**Decision.** Two People playbooks: `public_figure_profile` (public role, official accounts, statements, coverage, timeline) and `person_lookup` (stated legitimate purpose; work and role, professional profiles linked from captured pages, published work, news mentions attached through anchors, and only accounts the person has publicly linked to themselves). Never: guessing accounts from a matching name, collecting personal posts or photos, home, phone, family, routine or location, face matching, protected traits, minors. Never available to demo visitors.
**Why.** Professional lookups are common and legitimate; stalking-style aggregation is harmful and violates platform terms. Attribution through self-published links also prevents the most common error of name-based lookups — mixing up different people.
**Rejected.** Name-match account discovery across platforms; scraping platforms that forbid automated access.

### D23 — An Earth observation pack
**Decision.** Satellite imagery and disaster data are a first-class pack (P-EARTH): Copernicus Sentinel-1 radar and Sentinel-2 optical chips, NASA FIRMS and GIBS, GDACS, Copernicus EMS maps, ReliefWeb, rainfall history, and an `area_change` playbook. Change is measured by code; models only interpret the numbers.
**Why.** Event investigations such as floods are a core OSINT use and the original vision for Lantern; measured change is more reliable than a model looking at pictures.

### D24 — Free search by default
**Decision.** Tavily's free tier (1,000 searches a month, no card) is the default search provider; Brave is optional.
**Why.** Zero cost; Brave has no free plan and needs a card. Results stay transient with every provider (D10).

[ADR 0005 — Make the saved workspace setup satisfy the security policy](adr/ADR-0005-fresh-workspace-setup.md), accepted 2026-10-26, permits the narrow bootstrap devcontainer correction and corresponding S0.1-AC6/test amendment. Other shipped pack files and all quality gates remain protected.

[ADR 0006 — Continue with the existing workspace tool versions](adr/ADR-0006-existing-workspace-tool-versions.md), accepted 2026-10-26 by the user's explicit instruction, permits continuing M0 with the existing pinned development tools despite the recorded unresolved advisory matches. The Python dependency audit and all quality gates remain required.
