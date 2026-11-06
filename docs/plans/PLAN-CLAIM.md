# PLAN CLAIM — Check a claim

## Goal

Today Lantern researches open questions. This plan adds the second playbook of
`01_PRODUCT_SPEC.md` §7, `verify_claim`: the user pastes a claim, a post or a link, and
Lantern checks it the way a verification journalist would.

The agent works the four seed questions of `03_AGENT_DESIGN.md` §3:

1. **Origin.** Where and when did this first appear publicly, and who published it first?
2. **Support.** What do independent, reliable sources say about whether it is true?
3. **Prior checks.** Have established fact-checkers already assessed it or a close variant?
4. **Context.** Is genuine material being shown out of context (another time, place or event)?

It ends with a **verdict**: one of *Supported*, *False*, *Misleading* (real material, wrong
context) or *Unproven*. The model proposes the verdict; code decides whether the evidence
allows it. The verdict sentence goes through the same citation check as every report
sentence, for example: "It is very likely that the video shows an earlier flood."

The office rules stay exactly as they are:

- The model proposes; code decides.
- Every quote is checked against the saved source.
- Confidence is computed by code.
- Search results stay transient.
- Captured content cannot trigger any action outside the toolbox.

## Scope

**In (one pull request, `feature/claim-check`):**

| Part | What | Size (non-test lines, estimate) |
|---|---|---|
| Mode | `Investigation.mode` = `research` or `claim`; a "Check a claim" choice on the start form and `--claim` on the CLI | ~40 |
| Plan | The four seed questions are fixed by code; the model only writes their searches, phrases, the claimed date and place | ~50 |
| `fact_checks` tool | Searches the websites of established fact-checkers (a fixed list) through the existing web search; hits are leads to read, as with every search | ~70 |
| `earliest_copy` tool | The Wayback Machine's first saved copy of a known link: a record ("saved no later than …") plus the copy itself as a page to read | ~90 |
| Dated search | `news_search` and `web_search` accept optional `before` and `after` dates, so the agent can look for the same material before the claimed date | ~30 |
| Verdict | Pure rules in `core/verdict.py`; one model call proposes the label, likelihood and sentence; code downgrades a label the evidence does not carry | ~90 |
| Report and page | A verdict stamp at the top of the report page and in the Markdown report; "Claim check" on the case tiles | ~60 |

**Total: ~430 lines.**

**Later (a second, small pull request, only when the owner decides):**

- Google Fact Check Tools API (`claims:search`) as a second source for `fact_checks`. It needs
  a free Google API key that the owner would create and add as a Codespaces secret
  (`LANTERN_FACTCHECK_API_KEY`). Without the key, nothing changes.

**Out:**

- Reverse image search and video forensics. There is no free, permitted API for them. Image
  and video links stay leads for a person to check, for example with InVID.
- Face matching of any kind (invariant 3).
- Reading posts on sites whose terms forbid it (X, Facebook, Instagram, TikTok). They stay
  leads, as today.
- GDELT, which throttles this network.

## Design

### Mode and plan

- `Investigation` gets `mode: Literal["research", "claim"] = "research"`. Old saved
  investigations load unchanged.
- The safety gate runs first, as today. It already allows "checking public claims" and refuses
  claims about private individuals or minors. A test pins this down.
- In claim mode, `_plan` does not ask the model for key questions. Code writes Q1–Q4 from the
  seed questions, with the claim quoted. One model call (`CLAIM_PLAN`) returns:
  - up to N searches for each of Q1–Q4 (Q3 searches are phrased for fact-checkers);
  - ground-report phrases and hashtags, as today;
  - `claimed_date` (when the claim says it happened, or null) and `claimed_place`.
- Q1 and Q4 are `fact` questions. Q2 and Q3 are `fact` as well. There are no list questions.
- The researcher prompt gets one extra paragraph in claim mode: use `fact_checks` early, use
  `earliest_copy` on links given in the claim and on the earliest copies found, and search for
  the same material **before** the claimed date.

### `fact_checks` tool (`tools/adapters/factcheck.py`)

- Args: `query` (the claim in a few words, any language).
- Runs the existing Tavily search with `include_domains` set to a fixed list of established
  fact-checkers. The first list (re-checked against the IFCN signatory list during the build):
  - India: altnews.in, boomlive.in, factly.in, newschecker.in, vishvasnews.com,
    factcrescendo.com, newsmobile.in, thequint.com (WebQoof).
  - Global: snopes.com, politifact.com, factcheck.org, fullfact.org, factcheck.afp.com,
    leadstories.com, africacheck.org, chequeado.com, maldita.es, correctiv.org,
    logicallyfacts.com, rappler.com, misbar.com.
- Hits go back to the step only (transient), exactly like `web_search`. A fact-check counts as
  evidence only after Lantern reads and saves the page.
- These domains are rated **B** ("Established fact-checker") in `assessment.rate_source`, as in
  `04_DATA_SOURCES.md` §3.
- The extraction prompt gains one rule: on a fact-check page, the statement names the
  fact-checker and its rating ("Alt News rated the claim false because …"). That keeps
  fact-checkers' verdicts attributed.

### `earliest_copy` tool (`archive.py`, `tools/adapters/factcheck.py`)

- Args: `url`. The link must already be known to the investigation (invariant 5): written in
  the claim, found by a search, or linked from a saved page. The gateway's existing URL check
  enforces this.
- `Wayback.first(url)` asks the CDX index for the first capture with HTTP 200 (`limit=1`) and
  the number of captures.
- It returns a **record** source (kind `record`, origin `archive.org`, grade A as an archive
  capture, per `04` §3) with code-written statements, for example:
  "The Wayback Machine's earliest saved copy of <link> is from 3 August 2024." An archive
  capture proves "existed no later than" (`03` §8.7). It never proves "this is the original".
- For a page Lantern may read, the earliest copy itself is also saved as a page (with
  `archive_url` and `archived_at`), so its text can be quoted.
- For a post on a site whose terms forbid automated reading (see decision 2), only the capture
  **date** is read from the archive's index. The copy itself is never fetched.
- When nothing is archived, the result says so with its coverage: "The Wayback Machine has no
  saved copy of this link (checked 2026-11-06)." That is a statement about the search, not about
  the world (`03` §8.6).

### Dated search (`search.py`, `tools/adapters/web.py`)

- `NewsArgs` and `QueryArgs` gain optional `before` and `after` (YYYY-MM-DD dates).
- They map to Tavily's `end_date` and `start_date`. Tavily does not allow them together with
  `time_range`, so the args model refuses both at once with a plain message.

### Verdict (`core/verdict.py`, pure; `pipeline.py`)

- After the four findings are assessed, one model call (`VERDICT`) proposes:
  `label` (supported, false, misleading, unproven), `likelihood` (ICD 203 term), one verdict
  sentence, and the claim refs it rests on.
- Code decides (`core/verdict.py`, property-tested):
  - **Supported** needs the support finding (Q2) answered with at least two independent origins
    and no contradicting claim rated as high as its best supporter.
  - **False** needs either a fact-check claim (source rated B) that rates it false, or at least
    two independent origins against it.
  - **Misleading** needs the context finding (Q4) answered, with evidence of an earlier or
    different original (for example an archive record dated before the claimed date).
  - Anything else becomes **Unproven**, with the reason in plain words.
  - The likelihood is clamped by the existing `clamp_likelihood`; the confidence comes from the
    existing `confidence` rules. Both are stored, together with the proposed values.
- The verdict sentence passes `report.verify`: it must cite valid claims and must not mix a
  likelihood term with a confidence word. If it fails, the stamp shows the label alone, with
  "the verdict sentence was removed" in the removed list.
- New `Verdict` model on the investigation: `label`, `label_proposed`, `likelihood`,
  `likelihood_proposed`, `confidence`, `reason`, `sentence`, `cites`.

### Report and page

- The report page opens with a verdict stamp in the existing yellow and orange style: the
  label, the verdict sentence with its citations, and the confidence on its own line.
- The Markdown report starts with "Verdict: …".
- The four sections follow the seed questions, so a reader sees origin, support, prior checks
  and context in that order.
- Case tiles on the start page say "Claim check".

## Acceptance criteria

- CL-AC1 A claim-mode investigation plans exactly the four seed questions Q1–Q4, written by
  code; the model's plan output only adds searches, phrases, the claimed date and place.
- CL-AC2 The safety gate refuses a claim about a private individual or a minor, in claim mode
  as in research mode.
- CL-AC3 `fact_checks` searches only the fixed fact-checker domains, returns hits that are never
  stored, and its pages are rated B.
- CL-AC4 `earliest_copy` refuses a link the investigation does not know; returns a record whose
  statements are anchored in its saved text; for a site whose terms forbid reading, it reads
  only the capture date and never fetches the copy.
- CL-AC5 "No saved copy" is phrased as a statement about the search, with the date checked.
- CL-AC6 `before`/`after` reach the search as `end_date`/`start_date`; together with
  `time_range` they are refused with a plain message.
- CL-AC7 The verdict rules downgrade an unsupported label to *Unproven* with a reason
  (property tests over generated findings); likelihood is clamped and both values are stored.
- CL-AC8 The verdict sentence goes through the citation check; a sentence without valid
  citations is removed and the stamp shows the label alone.
- CL-AC9 The start form and the CLI start a claim check; the report page and the Markdown
  report show the verdict; old investigations without `mode` still load and render.
- CL-AC10 Captured text cannot change the verdict rules or call a tool outside the menu (an
  injection canary on a fake fact-check page).

## Test plan

- **Fakes, as today:** fake model, search, fetcher and archive. Scripted researcher steps for a
  full claim check (CL-AC1, CL-AC10).
- **Property tests:** the verdict rules (CL-AC7).
- **Recorded responses** through `scripts/record_fixture.py` (free, no AI tokens):
  - one Wayback CDX first-capture query (archive.org);
  - one Tavily search with `include_domains` and `end_date` (one search credit).
- **Existing suite:** stays green. The five tests that already fail on `main` (two need the
  Docker database, three are old M0 proof-kit tests) are unrelated.
- **One live claim check at the end**, quick depth, about 25–40k model tokens. Asked before it
  runs.

## External facts checked (2026-11-06)

| Source | Result |
|---|---|
| Tavily `/search` | `start_date` and `end_date` (YYYY-MM-DD) were added in July 2025 and filter by publish or last-updated date. They cannot be combined with `time_range` (docs.tavily.com changelog). `include_domains` is already used by `post_links`. Re-confirmed by the cassette. |
| Wayback CDX | `limit=N` returns the first N captures, oldest first. Lantern already uses `limit=-1` for the latest. Hard cap of 150,000 rows per query (github.com/internetarchive/wayback, CDX README). Re-confirmed by the cassette. |
| Google Fact Check Tools API | `v1alpha1/claims:search` is still the live path. It needs an API key, and Google's API terms apply. Only for the later pull request. |
| IFCN signatory list | Not confirmed online today. The list above is a starting point, re-checked against ifcncodeofprinciples.poynter.org during the build. |
| Fact-checker sites | Read like any page: robots.txt is respected, per-site limits apply, and refusals become leads. |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Token use.** One more model call (the verdict) and a fixed plan. | The plan call is smaller than today's, because the questions are fixed. The verdict is one short call. Quick and deep budgets stay as they are. |
| **Fact-checker sites refuse automated reading.** | robots.txt is respected; refused pages become leads; the Wayback copy is used when a site fails, as today. |
| **The model calls something "false" too easily.** | Code decides the label; weak evidence becomes *Unproven*; fact-checkers' ratings are attributed, never restated as fact. |
| **"No earlier copy found" read as "this is the original".** | The wording always names the tools used and the date checked (`03` §8.6). |
| **Claims about people.** | The gate refuses private individuals and minors; there are no new person pivots; record lookups stay limited to names in the evidence. |
| **Images and videos.** | Not analysed. They stay leads, and the report says so. |

## Rollback

- One pull request, revertible on its own.
- Research mode is unchanged. The new tools are listed only in claim mode's menu, and they
  can be switched off in settings.

## Decisions for the owner

1. **Fact-checker search without a Google key now**, and the Google Fact Check API as a small
   later pull request if you create the key. (Recommended.)
2. **For posts on sites Lantern does not read (X, Facebook, Instagram)**, `earliest_copy` reads
   only the date from the Wayback Machine's index, never the copy. This is the strongest
   evidence for "this video is older than claimed". (Recommended: yes.)
3. **The verdict labels**: Supported, False, Misleading, Unproven, decided by code rules.
   (Recommended.)

## Log

- Plan written 2026-11-06.
