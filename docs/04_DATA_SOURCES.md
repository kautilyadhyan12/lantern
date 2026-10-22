# 04 — Data Sources

Pack 3.0 · facts checked **2026-10-17 and 2026-10-22** on vendors' own pages unless marked *unverified* · status: reference (re-verify before each adapter story)

Prices, quotas and terms change. Every adapter story re-checks its rows (§12) and records the result, with URLs, in its PLAN. Each adapter also stores the price and limits it assumes, with the date checked, in its own module.

**Status**: ✅ build · ⚠️ build only under the stated conditions · ❌ do not build (use manual ingest or nothing). **Comm.**: usable in a commercial product under standard terms. **Rating**: default Admiralty reliability for content from this source (`03_AGENT_DESIGN.md` §8.1); record-level facts may rate higher.

## 1. Model providers (checked 2026-10-22)

All are reached through OpenAI-compatible APIs (`02` §11). Free-tier limits change often; S1.8 re-verifies them and records them in `src/lantern/data/models.yaml`.

| Provider | Status | Models (examples) | Free limits | Output control | Data | Notes |
|---|---|---|---|---|---|---|
| Groq | ✅ default free | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b` (preview), `llama-3.3-70b-versatile`, `llama-3.1-8b-instant` | gpt-oss-120b, gpt-oss-20b, qwen3.8-27b: 30 requests/min, 1,000/day, 8,000 tokens/min, 200,000 tokens/day each (the page's labelling of free vs developer limits is ambiguous: check the account's limits page) | `json_schema` strict on gpt-oss and qwen3.8; `json_object` on all | no retention by default; logs up to 30 days for abuse review | console.groq.com/docs/rate-limits · /structured-outputs |
| Cerebras | ✅ free | `gpt-oss-120b`, `qwen-3.8-27b` | 5 requests/min, 1,000,000 tokens/day (also per hour) | `json_schema` strict | does not retain inputs and outputs | inference-docs.cerebras.ai/support/rate-limits |
| OpenRouter `:free` models | ✅ free, rotating | the free list rotates (October 2026: NVIDIA Nemotron 3, MiniMax M3.1 Flash and others; `gpt-oss-120b:free` listed on its own page) | 20 requests/min; 50/day, or 1,000/day after buying 10 credits once | varies by model | providers that log or train are excluded unless the account allows them | openrouter.ai/docs/api-reference/limits — re-query the free list before use |
| NVIDIA build (NIM trial) | ⚠️ development and testing only | `deepseek-ai/deepseek-v4.1-flash`, GLM-5.3 variants, Nemotron | per-account limits shown in the console | *unverified* | trial terms | Trial terms allow development, testing, research and evaluation only, so the public demo never uses it. |
| DeepSeek official API | ⚠️ optional, paid | `deepseek-flash` (V4.1 Flash), `deepseek-v4-pro`; 1M context | no free credit found | `json_object` only (no `json_schema`); tool calls supported | terms silent on training with API data | `deepseek-flash` per 1M tokens: cache hit $0.003, miss $0.15, output $0.60 off-peak; double at peak (01:00–04:00 and 06:00–10:00 UTC on weekdays). api-docs.deepseek.com/quick_start/pricing |
| Local (Ollama, vLLM) | later | any open-weight model | free; needs a machine with enough memory (not the 4 GB laptop) | depends on server | stays on the machine | same OpenAI-compatible interface |

The coding agent (Codex, signed in with a ChatGPT plan) is separate from these: it builds Lantern, it is not part of Lantern.

## 2. Web search and page fetching

| Source | Status | Access | Cost and limits | Comm. | Notes |
|---|---|---|---|---|---|
| Brave Search API | ⚠️ M1 optional (needs a card) | API key | No free plan since Feb 2026; $5 per 1,000 queries; $5 monthly credit; 50 req/s | yes, own apps | Terms (1 Sep 2026) forbid storing or caching results, AI training and resale → results stay transient (`02` §8.1). api-dashboard.search.brave.com/documentation/pricing · …/terms-of-service |
| Tavily | ✅ M1 default (free, no card) | API key | 1,000 free credits/month; pay-as-you-go $0.008/credit (1 search = 1 credit); dev key 100 req/min | internal business use | Terms say Tavily may use customer data — do not send sensitive queries through it (§13). docs.tavily.com/guides/api-credits · tavily.com/terms |
| Exa | ⚠️ later, optional | API key | $10 monthly credit; $4–15 per 1,000 by mode | yes | Terms bar copying or storing outputs → transient only. exa.ai/docs/reference/pricing |
| Serper.dev, SerpApi (Google results) | ❌ | API key | Serper "from $0.30/1k"; SerpApi $25/1k | — | Legal exposure: Google v. SerpApi (filed 19 Dec 2025; claims dismissed 20 Jul 2026, amended complaint 10 Aug, new dismissal motion pending). serpapi.com/pricing |
| Own fetcher (SafeTransport + trafilatura + pypdf) | ✅ M1 | none | free | yes | First-hand capture is the evidence. Respects robots.txt, identifies itself, rate-limited per host. |
| Jina Reader, Firecrawl (hosted fetch proxies) | ❌ default | API key | free tiers | unclear / restricted | A proxy's copy is not a first-hand capture; Firecrawl terms restrict commercial use (revised 7 Oct 2026); Jina terms unclear after its acquisition by Elastic. |
| Anthropic server-side web search | ❌ default | — | $10/1,000 + tokens | yes | Results bypass the tool gateway's capture and provenance rules. |

## 3. News, fact-checks, archives, reference

| Source | Status | Access | Cost and limits | Comm. | Rating | Notes |
|---|---|---|---|---|---|---|
| GDELT DOC 2.0 API | ✅ M2 | none | free; `maxrecords` ≤ 250; no published rate limit — self-limit to 1 request / 5 s | yes, with citation and link | metadata C; linked article rated by its outlet | Operating (live response 2026-10-17). Results may be stored with attribution. blog.gdeltproject.org/gdelt-doc-2-0-api-debuts |
| Google Fact Check Tools API (`claims:search`) | ✅ M2 | API key | free; quotas undocumented | Google API terms | established fact-checkers B | API is v1alpha1 and live; ClaimReview stopped showing in Google Search in 2025 but the API remains. developers.google.com/fact-check/tools/api/reference/rest |
| Publisher RSS/Atom feeds | ✅ M2 | none | free | per publisher | by outlet | Curated feed lists per region (P-INDIA adds Indian outlets in several languages). |
| Wayback Availability + CDX APIs | ✅ M2 | none | free; CDX ≤ 150,000 rows per query; be polite | *unverified* | archive capture = record A ("existed no later than") | archive.org/help/wayback_api.php · github.com/internetarchive/wayback (CDX README) |
| Wayback Save Page Now 2 | ✅ M2 | S3-style keys (`Authorization: LOW access:secret`) | authenticated: 7 captures/min, 30,000/day, 5/day per URL (anonymous: 3/min, 200/day) | *unverified* | — | Background job; never blocks a run. SPN2 public doc (updated 22 Jul 2026). |
| Common Crawl CDX index | ⚠️ later | none | free; heavily rate-limited, numbers unpublished | terms neither permit nor forbid | B (existence) | Newest index CC-MAIN-2026-39. commoncrawl.org/faq |
| Wikipedia / Wikidata | ✅ M2 | none; User-Agent `Client/version (contact)` required | free; WDQS 60 s query limit; stricter limits for non-compliant agents since Jan 2026 | content CC BY-SA | C, background only | Scholarly data split to a separate query endpoint (Jan 2026). wikitech.wikimedia.org/wiki/Robot_policy |

## 4. Social platforms (P-SOCIAL; re-check terms at epic start)

| Platform | Status | Access | Limits | Comm. | Rating | Notes |
|---|---|---|---|---|---|---|
| Bluesky (AT Protocol) | ⚠️ | public AppView for profiles and threads; **post search needs an authenticated account** (unauthenticated search mostly disabled) | PDS: 3,000 requests / 5 min / IP; AppView limits unpublished | terms silent on API use | record A (post exists/time); content D, C for identified organisations | Use the user's **own** account with an app password — never a created persona. Respect `!no-unauthenticated` and moderation labels. docs.bsky.app/docs/advanced-guides/rate-limits |
| Mastodon / fediverse | ✅ | public and hashtag timelines without a token (unless the instance disables public preview); search without auth covers accounts and hashtags only | 300 requests / 5 min per IP | per instance terms | record A; content D | Honour `discoverable: false` and `noindex`; respect each instance's terms. docs.joinmastodon.org/api/rate-limits |
| YouTube Data API v3 | ✅ | API key | 10,000 units/day; `search.list` has its own bucket of 100 calls/day (since 1 Jun 2026) | yes | record A; content D (C for identified channels) | Data from non-authorised users may be cached **≤ 30 days** → retention rule (S2.12-AC3). No transcript scraping. developers.google.com/youtube/v3/determine_quota_cost |
| Reddit Data API | ⚠️ only after written approval | OAuth; explicit approval required for any API use (Responsible Builder Policy) | 100 queries/min per client | contract required | content D | Terms forbid inferring sensitive traits or re-identifying users; deleted content must be purged. support.reddithelp.com (Responsible Builder Policy) |
| X API | ⚠️ later, content search only | prepaid credits | pay-per-use: $0.005 per post read, $0.010 per user (24 h de-dup); recent search covers 7 days, 450 requests / 15 min | restricted | content D | Restricted-use policy forbids surveillance, profiling and "investigating or tracking X users", and requires deletion within 24 h. Only event/content search, never user-centric work; approval-gated; terms re-checked first. docs.x.com/x-api/getting-started/pricing · docs.x.com/developer-terms/restricted-use-cases |
| Telegram | ❌ automated | — | — | — | — | API terms ban AI/ML use and the general terms forbid scraping. Users may ingest public posts manually. core.telegram.org/api/terms |
| Threads | ❌ | keyword search needs App Review | 2,200 queries/day | Meta terms forbid surveillance tools and profile building | — | developers.facebook.com/docs/threads/keyword-search |
| TikTok Research API, Meta Content Library | ❌ | eligible academic or non-profit researchers only | — | non-commercial | — | Eligible researchers may use them outside Lantern and ingest results manually. |
| Instagram, Facebook, LinkedIn | ❌ | no compliant API for this use | — | — | — | Manual ingest only. |
| Username checks across sites | ⚠️ `self_audit` only | public profile URLs | ≤ 1 request/s per site | own requests | record D | Only the user's own identifiers; existence checks only; robots.txt and site terms respected. |

## 5. Organisations and sanctions (P-ORG)

| Source | Status | Access | Limits | Comm. | Rating | Notes |
|---|---|---|---|---|---|---|
| GLEIF LEI API | ✅ | none | 60 requests/min | yes (CC0) | A | Possible interruptions 19 Oct–4 Nov 2026. gleif.org/en/meta/lei-data-terms-of-use |
| UK Companies House API | ✅ | API key as HTTP Basic username | 600 requests / 5 min | yes | A | Officer occupation field removed Oct 2025. developer-specs.company-information.service.gov.uk |
| SEC EDGAR (`data.sec.gov` submissions and company facts; nightly bulk files) | ✅ | none; declared User-Agent `Company contact@domain` | 10 requests/s | yes | A | EDGAR **full-text search has no documented API** → not automated. sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data |
| OFAC SDN and consolidated lists | ✅ | none; User-Agent required | not stated | yes | A | XML, CSV, Advanced XML via sanctionslistservice.ofac.treas.gov |
| UN Security Council consolidated list | ✅ | none | not stated | check site terms for redistribution | A | scsanctions.un.org/resources/xml/en/consolidated.xml |
| EU financial sanctions (FSF) | ⚠️ | download token (EU Login) | not stated | licence not stated | A | Official Journal is authoritative; the FSF file can lag. |
| OpenSanctions | ⚠️ | API key (credits) or bulk download | API credits (1-year): 500 = €50 … 100k = €5,000 | **API: yes**; bulk data CC BY-NC; serving customers from self-hosted bulk data (yente) needs a reseller licence | A (aggregated official lists) | Free API keys for journalists, NGOs and academics. Non-commercial mode: bulk + yente; commercial mode: API credits or licence. opensanctions.org/licensing |
| OpenCorporates | ⚠️ | API token | default 200 requests/month, 50/day; free share-alike keys; free at-scale access on request for journalists, NGOs, universities; paid from £2,250/year | free keys: ODbL share-alike only | A | opencorporates.com/pricing |
| India MCA21 | ❌ API | portal only (no official API found) | — | — | A | Manual pivots to the MCA portal. |
| data.gov.in company master data | ⚠️ P-INDIA | API key (*unverified*) | *unverified* | licence not shown | A | Registrar-wise company master data (CIN, status, capital, address; no directors). |

## 6. Infrastructure (P-INFRA)

| Source | Status | Access | Limits | Comm. | Rating | Notes |
|---|---|---|---|---|---|---|
| RDAP | ✅ | none; IANA bootstrap files (RFC 9224) | registry-specific; rdap.org redirector 10 requests / 10 s | registry terms | A | gTLD WHOIS (port 43) obligation ended 28 Jan 2025 → RDAP first. data.iana.org/rdap |
| DNS (dnspython) | ✅ | none | resolver limits | yes | A (record at time of query) | DNS is not HTTP: lookups go through a dedicated resolver function with its own policy and logging. |
| crt.sh (certificate transparency) | ⚠️ | none; JSON output undocumented | ~60 requests/min/IP; 10,000-row cap; frequent timeouts | no terms found | A | Small queries, aggressive caching. |
| urlscan.io | ⚠️ | API key | free plan: 1,000 searches/day, 5,000 public scans/day | day-to-day investigations yes; embedding data in a product needs an agreement | B | Search by default; submitting a scan publishes the URL → approval required. urlscan.io/docs/api |
| VirusTotal public API | ⚠️ non-commercial | API key | 500 requests/day, 4/min | **no** ("must not be used in commercial products") | B | Disabled in commercial mode. docs.virustotal.com/reference/public-vs-premium-api |
| Shodan | ⚠️ optional | API key | membership $49 one-off (100 query credits/month); plans from $69/month; 1 request/s | paid plans; attribution | B | account.shodan.io/billing |

## 7. Maps, imagery and environment (P-MEDIA, P-MOVE)

| Source | Status | Access | Limits | Comm. | Notes |
|---|---|---|---|---|---|
| Nominatim (public instance) | ⚠️ light use | none; real User-Agent | 1 request/s; no bulk; recurring scripts ≤ 4/min | geocoding-centred services must run their own instance | operations.osmfoundation.org/policies/nominatim |
| Overpass API (public) | ⚠️ light use | none | guideline ≈ 10,000 queries and 1 GB/day | commercial use should self-host or pay | Public main instance has been unreliable since late 2025. |
| Mapillary API v4 | ✅ | client token | generous; bbox < 0.01 square degrees | allowed; imagery CC BY-SA; no re-identification | Attribution required. mapillary.com/developer/api-documentation |
| Copernicus Data Space (Sentinel) | ✅ | free account | e.g. 10,000 Sentinel Hub requests/month | Sentinel data free and open | documentation.dataspace.copernicus.eu/Quotas.html |
| NASA FIRMS (fires) | ✅ | free MAP_KEY | 5,000 transactions / 10 min; ≤ 5 days per request | open data policy | MODIS satellites expected to retire late 2026–early 2027 (VIIRS continues). |
| Open-Meteo historical weather | ⚠️ non-commercial free | none (key for paid) | free < 10,000/day, 5,000/h, 600/min | free tier non-commercial; historical API needs a paid Professional plan for commercial use | open-meteo.com/en/terms |

### 7.1 Earth observation and disasters (P-EARTH, checked 2026-10-22)

| Source | Status | Access | Free limits | Terms | Notes |
|---|---|---|---|---|---|
| Copernicus Data Space — Sentinel Hub Process API | ✅ | free account; OAuth tokens valid 10 min | 10,000 requests and 10,000 processing units per month; 300 requests/min | Sentinel data free and open | Before/after image chips for an area: Sentinel-1 radar (sees water through cloud) and Sentinel-2 optical. documentation.dataspace.copernicus.eu/Quotas.html |
| Copernicus Data Space — STAC catalogue | ✅ | `https://stac.dataspace.copernicus.eu/v1/` | per-connection bandwidth limits | free and open | Finds which scenes exist for a place and date (`sentinel-1-grd` confirmed; the Sentinel-2 collection id is checked in the epic). The old catalogue endpoint is deprecated. |
| Copernicus Data Space — openEO | ⚠️ optional | free account | 10,000 credits/month; 2 concurrent jobs | free and open | Server-side processing if simple chips are not enough. |
| Copernicus Emergency Management (rapid mapping) | ✅ read-only | public activation pages and products | — | free with attribution; some products for registered users only | Only authorised bodies can request mapping; anyone can use published maps as A-rated sources. mapping.emergency.copernicus.eu |
| NASA FIRMS (active fires) | ✅ | free MAP_KEY | 5,000 transactions / 10 min; 1–5 days per query | open data | VIIRS (several satellites) and MODIS. firms.modaps.eosdis.nasa.gov/api/area |
| NASA GIBS (daily global imagery tiles) | ✅ | none | — | acknowledgement required | Quick daily views for timelines. nasa-gibs.github.io/gibs-api-docs |
| GDACS (global disaster alerts) | ✅ | none | 100 records per page | cite GDACS | Floods, cyclones, earthquakes as GeoJSON events: a good starting point for `reconstruct_event`. |
| ReliefWeb API v2 | ⚠️ | pre-approved `appname` required since 1 Nov 2025 | 1,000 calls/day | partner content may be copyrighted | Humanitarian situation reports; apply for an appname at the start of the epic. apidoc.reliefweb.int |
| Open-Meteo historical weather | ⚠️ non-commercial free | none | < 10,000/day | non-commercial | Rainfall before a flood (see §7). |

### 7.2 People (P-PEOPLE, checked 2026-10-22)

| Source | Status | Use | Notes |
|---|---|---|---|
| Web search + first-hand fetch (§2) | ✅ | finding pages about a person | Only pages that allow automated access are fetched. Profile links on platforms that forbid automated access (LinkedIn, Instagram, Facebook) are shown only when a captured page links to them (`03` §8.8). |
| Personal websites, company team pages, conference and university pages | ✅ | anchors and self-published links | Main evidence for `person_lookup`. |
| Wikidata / Wikipedia | ✅ | public figures: identity, positions, official websites and accounts | Background only for confidence, but good for disambiguation. |
| Official government and parliament sites | ✅ | public office holders | Primary records (A). |
| Platform official APIs (Bluesky, Mastodon, YouTube, GitHub public profiles) | ⚠️ | checking that an account links back to a known page | Terms re-checked in the epic; never used to collect someone's posts into a profile. |
| News search (GDELT, fact-checks) | ✅ | coverage and mentions, attached only through anchors | |
| People-search sites, data brokers, breach data | ❌ | — | Never (`07` invariant 4). |

## 8. Aviation and maritime (P-MOVE)

| Source | Status | Access | Limits | Comm. | Rating | Notes |
|---|---|---|---|---|---|---|
| OpenSky Network REST API | ⚠️ non-commercial | OAuth2 client credentials only (basic auth ended 18 Mar 2026) | 4,000 credits/day registered (400 anonymous); `/states/all` ≤ 1 h back; tracks ≤ 30 days | **no** — non-profit research and education only | B (A with several receivers) | Some cloud IP ranges are blocked. openskynetwork.github.io/opensky-api/rest.html |
| adsb.lol | ⚠️ | live API without key (licence *unverified*); daily history archives on GitHub | dynamic | archives ODbL | B | github.com/adsblol/api · github.com/adsblol/globe_history_2026 |
| airplanes.live | ⚠️ non-commercial | none | 1 request/s | no | B | airplanes.live/api-guide |
| adsb.fi open data | ⚠️ non-commercial | none | 1 request/s; IP bans for abuse | personal, non-commercial; must cite | B | github.com/adsbfi/opendata |
| AISStream.io | ⚠️ | API key | 3 connections per account; bandwidth limits on uncompressed streams since Sep 2026 | *unverified* | B | Live only, no history. aisstream.io/documentation |
| Global Fishing Watch | ⚠️ non-commercial | free token | 50,000 requests/day | CC BY-NC | B | Credit "Powered by Global Fishing Watch". |

## 9. Media tooling (P-MEDIA)

| Tool | Status | Facts | Notes |
|---|---|---|---|
| ExifTool | ✅ | 13.59 (May 2026); Perl Artistic or GPL | Run as a separate process with argument lists; never a shell string. |
| `c2pa-python` | ✅ | 0.38.0 (29 Sep 2026); MIT or Apache-2.0; pre-1.0 with breaking changes | Pin the version. |
| TinEye API | ⚠️ paid | prepaid bundles (example on its help pages: 5,000 searches for $200); commercial use offered | Optional; approval-gated. |
| SerpApi Google Lens | ❌ | $25 per 1,000 | Same legal exposure as §2. |
| Assisted manual reverse-image search | ✅ default | free | Lantern opens Google Lens, Yandex, Bing and TinEye in the user's own browser; the user pastes results back as sources. |

## 10. Libraries and services checked (versions on 2026-10-17)

| Component | Version | Licence | Notes |
|---|---|---|---|
| DBOS Transact (`dbos`) | 3.3.0 (2026-10-15) | MIT | Async workflows and steps; durable `send`/`recv`; queues with concurrency and rate limits; 3.0 (2026-09-16) changed APIs; Windows support not stated → S2.1 spike. |
| Procrastinate | 3.10.0 | MIT | Fallback job queue; Postgres 13+. |
| trafilatura | 2.3.1 | Apache-2.0 (since 1.8.0) | |
| warcio | 1.8.1 | Apache-2.0 | |
| WACZ spec / `wacz` | 1.1.1 / 0.6.0 | `wacz` licence metadata inconsistent (Apache-2.0 vs MIT) | Optional WACZ export later. |
| ReplayWeb.page | 2.5.3 | AGPL-3.0 | Users may open exported WARC/WACZ in it; do not embed it in Lantern. |
| `rfc3161-client` | 1.0.9 | Apache-2.0 | Require ≥ 1.0.3 (earlier versions had a critical signature-check flaw). |
| freeTSA.org | — | free incl. commercial, best effort, 1 request/s | New certificates since Mar 2026; fetch current CA files. |
| import-linter | 2.15 | BSD-2-Clause | |
| fastembed | 0.9.0 | Apache-2.0 | ONNX runtime, no PyTorch — use when embeddings are needed. |

## 11. Personal versus commercial use

Lantern is a personal, non-commercial tool, so the sources marked non-commercial are generally usable — **within each source's own wording**, which is not always "personal use": OpenSky says non-profit research and education; adsb.fi says personal, non-commercial; OpenSanctions bulk data is CC BY-NC; Open-Meteo's free tier and VirusTotal's public API are non-commercial; Global Fishing Watch is CC BY-NC. Each adapter story quotes the relevant wording in its PLAN.

Personal use does not relax the rest: rate limits, attribution, storage and caching rights (search results stay transient), retention limits, and restricted uses such as surveillance or profiling all still apply. Reddit still needs written approval for any API use.

Each adapter still declares `licence.commercial_ok`, so if Lantern ever became commercial, the non-commercial sources could be switched off in one place (OpenSky REST, airplanes.live, adsb.fi, Global Fishing Watch, Open-Meteo free tier, VirusTotal public API, OpenSanctions bulk data and self-hosted yente, OpenCorporates free keys, urlscan.io data in a product, heavy use of public Nominatim and Overpass).

## 12. Re-verify checklist (first step of every adapter story)

1. Pricing page URL and current prices.
2. Authentication flow.
3. Rate limits and quotas.
4. Terms: commercial use, **storage and caching rights**, retention limits, attribution, restricted uses (surveillance, profiling, re-identification).
5. Record fresh cassettes and confirm the response schema matches the adapter models.
6. Write findings with URLs and the date into the PLAN and the adapter's metadata.

## 13. Operational security of queries

Every search query and fetch tells a third party what is being investigated. Lantern logs exactly what it sent where (`search_log`, `tool_calls`), prefers providers with strong privacy terms, never sends evidence text to a search provider, and supports an optional outbound proxy setting for users who need to separate investigations from their own network identity. Users investigating sensitive subjects should be told this plainly in the brief screen (M3).
