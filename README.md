# Lantern

Lantern is an open-source intelligence (OSINT) research tool that answers questions
using only public information, and produces reports where every sentence can be checked
against the evidence behind it.

You ask a question. Lantern:

1. **Checks it is safe to research.** Fixed rules, then a model check, refuse questions
   that target private people, locate or track anyone, involve minors, or seek private data.
2. **Splits it into key questions** (`Q1`, `Q2`, …) that together answer it.
3. **Investigates in rounds.** It searches the web and the news (within the period the
   question covers, and in local languages where useful), lets the model choose the most
   promising results, then reviews what it found and follows up: single-source items,
   missing incidents, other names and spellings, and primary sources. A deep investigation
   runs up to three rounds and 30 pages; a quick look runs one. For questions that ask for
   every instance, it keeps a list of everything found, each item marked corroborated or
   single source. It reads pages politely: it only opens links returned by search,
   obeys robots.txt, identifies itself, and never connects to private or internal network
   addresses. Search results themselves are never stored.
4. **Adds ground reports from public social media.** Bluesky public search and Mastodon
   hashtag timelines supply first-hand posts about the event, graded D (unverified) until
   other sources confirm them. Only event searches are made, never an account's timeline;
   opted-out accounts and labelled posts are skipped, authors are not stored, and each
   account counts once towards corroboration.
5. **Preserves every source** (`S1`, …) with the sha256 fingerprint of the bytes it saved.
6. **Extracts claims anchored to exact quotes** (`C1`, …). Code checks that each quote
   appears word for word in the saved page; claims whose quotes cannot be found are dropped.
7. **Assesses each key question with rules, not model opinion.** Sources get Admiralty
   reliability grades (A–F) from a fixed table; corroboration counts independent websites
   only; likelihood uses the seven ICD 203 terms and is toned down when evidence is thin;
   analytic confidence (low, moderate, high) is computed by code.
8. **Writes a verified report.** Every sentence must cite existing claims; sentences that
   do not are removed and listed. Each citation opens the exact quote, highlighted inside
   the saved copy of its source.

## Try it

Lantern needs two free API keys, added as **Codespaces secrets** (GitHub → Settings →
Codespaces → Secrets) and then a codespace restart:

| Secret | Used for |
|---|---|
| `LANTERN_TAVILY_API_KEY` | web search (Tavily free tier) |
| `LANTERN_GROQ_API_KEY` and/or `LANTERN_CEREBRAS_API_KEY` | open-weight models (`gpt-oss-120b`) on free tiers, with automatic fallback |
| `LANTERN_GEMINI_API_KEY` (optional) | backup model on Google's free tier, used only when the others are at their limits; free-tier prompts may be used by Google, so only public material is ever sent |

```sh
uv sync --frozen
uv run lantern serve                      # web app on http://127.0.0.1:8000
uv run lantern run "What is publicly known about the 2026 Assam floods?"
```

In a codespace, open the **Ports** tab to view the web app in your browser. Each
investigation is capped (key questions, pages and model calls) and there is a daily limit,
so free quotas last. Captured evidence is stored under `var/`, which is never committed.

## How it is built

| Part | Module |
|---|---|
| Investigation flow | `src/lantern/pipeline.py` |
| SSRF-safe fetching, robots.txt, pacing, size limits | `src/lantern/egress.py` |
| Quote anchoring with an offset map | `src/lantern/text.py` |
| Ratings, independence, confidence, likelihood limits | `src/lantern/assessment.py` |
| Fixed safety rules | `src/lantern/safety.py` |
| Social ground reports (Bluesky, Mastodon) | `src/lantern/social.py` |
| Model gateway: validated JSON, one retry, provider fallback | `src/lantern/llm.py` |
| Citation checks and Markdown export | `src/lantern/report.py` |
| Web app (FastAPI) | `src/lantern/web/` |

Every model reply must be a single JSON object that validates against a Pydantic model;
an invalid reply gets one retry, then the step fails with a plain message. Page text is
treated as untrusted data, and the steps are a fixed sequence, so content on a web page
cannot make Lantern take any other action. The design documents are in `docs/`.

## Development

Open the repository on GitHub, choose **Code → Codespaces → Create codespace**,
and work in your browser. The container provides Python 3.12, uv and Docker.
The owner's development rules are in AGENTS.md; API keys belong in Codespaces secrets.

```sh
uv sync --frozen
uv run pytest tests/research        # offline tests with fake model, search and pages
make db
export LANTERN_DATABASE_URL='postgresql+asyncpg://lantern:lantern-local-only@127.0.0.1:5434/lantern'
uv run lantern db upgrade
make hooks
make check
```

These public credentials are for local development only; never reuse them for deployment.
The database listens on localhost port 5434. Run `make db` to start it, or `make db-down`
to stop it while keeping its data. Real secrets come from environment variables;
.env.example has placeholders. Never commit captured evidence or personal data to this
public repository.
