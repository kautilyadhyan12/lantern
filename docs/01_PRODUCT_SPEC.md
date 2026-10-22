# 01 — Product Specification

Pack 3.0 · written 2026-10-22 · status: source of truth (change only through a decision record, see `09_DECISIONS.md`)

## 1. The product in one paragraph

Lantern is an **open-source intelligence (OSINT) investigation platform**: it investigates questions using only publicly available information — the web, news, social media posts, satellite images, aircraft and ship tracking, company and domain records. You give it a brief — "What happened in the Nepal floods and how bad was it?", "Is this viral video really from yesterday?", "Which aircraft circled this area on Tuesday?", "Who runs this company?", "Who is this public figure and what have they said?" — and it works the way a disciplined analyst works. It breaks the brief into **key questions**, gathers public evidence through audited tools, **preserves every source it uses**, extracts **claims tied to exact quotes**, counts only **independent** evidence as corroboration, states its uncertainty in **standard analytic language**, and hands back a report in which every sentence is traceable to preserved evidence and has been **checked against that evidence before publication**.

## 2. Why this should exist

General "deep research" assistants are fast and fluent. They are weak exactly where investigators need strength.

| Investigator need | General research assistants | Lantern |
|---|---|---|
| Every statement traceable | Links to pages, rarely to the passage | Each sentence cites claims; each claim cites an exact quote in a preserved copy |
| Evidence survives deletion | Not preserved | Captured and hashed when used; WARC file locally; optional Wayback copy |
| Honest uncertainty | Confident prose | Source ratings (Admiralty A–F), likelihood terms (ICD 203), analytic confidence computed by rules |
| Independence | Twenty articles repeating one post look like corroboration | Copies, syndication and "according to X" chains count once |
| Specialist public records | Rarely used | Fact-check databases, archives, registries, certificate logs, flight/ship data (packs) |
| Reproducibility and audit | None | Append-only, hash-chained event log; replayable runs; evidence bundle export |
| Ethics and law | Generic | Purpose gate, public-data-only tools, no face recognition, no stalking-style profiling, minors protected |

Classic OSINT tools (link-analysis and recon frameworks) collect data at scale but leave the reasoning to the analyst. Lantern's bet: the scarce resource is **trustworthy analysis**, not more data.

## 3. Who it is for

Lantern is a **personal project** with a **public demo**: you use it fully; recruiters and other visitors can open the demo site, replay recorded investigations and run a few limited live ones (§6, M5 demo). The kinds of work below are the jobs it is designed to do well, not separate customers.

Design for these first:

- **Fact-checkers and verification journalists** — verify claims and media, trace where something first appeared, reconstruct events. Multilingual evidence is normal (for example English plus Hindi, Bengali or Assamese for an event in Assam).
- **Due-diligence and compliance analysts** — identify organisations, their officers in their professional role, sanctions exposure, litigation and adverse media.

Then:

- **Security and threat-intelligence researchers** — domains, infrastructure, campaigns (organisation and infrastructure level, never unmasking private people).
- **Researchers and NGOs** — documented, reproducible public-source research; topic monitoring.

People are supported in two clearly bounded ways: **public figures** in their public role, and a **professional person lookup** for ordinary people (work, professional profiles, published work, news mentions, and only the accounts a person has publicly linked to themselves). Not for anyone trying to locate, track, stalk or unmask a private person. See §7, §8 and `07_SAFETY_LEGAL.md`.

## 4. Core concepts (use these exact names in code, UI and docs)

| Term | Meaning |
|---|---|
| **Investigation** | A case: brief, policy decision, budget, questions, sources, claims, findings, reports, event log. |
| **Brief** | What the user asks: objective, purpose, scope (time window, places, languages, subjects), seed inputs (URLs, names, files), constraints. |
| **Purpose** | Declared lawful purpose: `journalism`, `research`, `due_diligence`, `security_research`, `professional_lookup`, `self_audit`, `other_lawful`. Drives policy. |
| **Playbook** | A versioned template: seed questions, allowed tools, limits, approval rules, report outline. A starting point, not a script. |
| **Question (Q)** | A key question the investigation must answer, with kind, priority, status and answer criteria. |
| **Source (S)** | One captured artifact (page, API record, post, document, upload). Immutable, hashed, preserved. Search results are never Sources (`02` §8.1). |
| **Origin** | A group of sources or claims that are not independent of each other (copies, syndication, the same original speaker). |
| **Claim (C)** | One atomic assertion. A *content claim* is something a source says, anchored to a verbatim quote. A *record claim* is a fact about the source itself (who published it, when), derived by code from metadata. |
| **Entity (E)** | What claims are about: organisation, person (public role only), place, event, domain, account, vessel, aircraft, document, media item. |
| **Finding (F)** | The current answer to a question: statement, likelihood, analytic confidence, supporting and contradicting claims, short rationale. |
| **Hypothesis (H)** | A competing explanation tested with Analysis of Competing Hypotheses (ACH) when evidence conflicts. |
| **Report** | A verified rendering of findings, with bottom line, method, gaps and evidence appendix. |
| **Event** | An append-only, hash-chained record of everything that happened: tool calls, model calls, policy decisions, user actions. |
| **Run** | One durable, resumable execution of the investigation workflow. |
| **Pack** | A vertical bundle of adapters, playbooks and evals (Earth observation, Media, People, Movement, Organisations, Infrastructure, Social, Regional India). |

Short refs (`Q3`, `S12`, `C47`, `F2`, `H1`, `E5`) are unique within an investigation. Reports and everything the model reads or writes use these refs, never UUIDs.

## 5. What a user experiences

1. Write a brief, choose a purpose, pick a playbook (or accept the suggested one).
2. See the policy result: allowed, allowed with restrictions, needs your attestation, or denied — with reasons.
3. Review the proposed key questions: edit, add, remove (interactive mode).
4. Watch the run: questions move from open to answered or unanswerable; sources are captured; spend is shown; premium steps (expensive per call, or with side effects such as publishing a scan) wait for approval.
5. Read the report: bottom line first; one finding per question in calibrated language; every citation opens the exact quote inside the preserved source; contradictions and alternative explanations; what could not be determined and why; method and source ratings.
6. Correct and continue: reject a claim, change a source rating with a reason, add a source, add a question. Re-running updates findings; corrections are logged.
7. Export: Markdown, self-contained HTML, JSON, and an **evidence bundle** (sources, hashes, audit chain, optional trusted timestamp).
8. Keep watching: turn an investigation into a monitor that alerts you when something new appears.

### 5.1 Two examples, start to finish

**An event.** Brief: *"Floods in eastern Nepal, 20–25 September 2026: what happened, where, how bad?"* Lantern plans key questions (When did it start? Which districts? How many affected, according to whom? What do satellite images show?), searches news and GDELT in English and Nepali, pulls official updates, compares Sentinel-1 radar images from before and after (radar sees water through clouds) and Sentinel-2 photos when skies are clear, checks rainfall history, and finds relief flights in aircraft tracking data. The report shows a timeline, a map of flooded areas, casualty figures with who reported them and how far they agree, and what could not be confirmed.

**A claim.** Brief: *"A video says it shows Guwahati flooding yesterday — is it real?"* Lantern traces the earliest copy, finds it posted two years earlier about a different flood, checks fact-checkers, and reports: *It is very likely that the video shows an earlier flood.* followed by a separate confidence sentence — every fact clickable down to the quote in a saved copy of the page.

## 6. Releases

| Release | Name | What the user gets |
|---|---|---|
| M0 | Foundation | Tooling, workflow, CI. No product features. |
| M1 | Walking skeleton | `lantern run "<brief>"` → cited report from web search and fetch, command line only. |
| M2 | Trustworthy core | Durable runs, policy gate, independence and contradictions, assessment standard, ACH, verification gate, preservation, news and fact-check sources, evidence bundle, evals. |
| M3 | Workspace | Web app: briefs, live runs, approvals, report with citation cards, evidence review and corrections, timeline and ACH views. |
| M4 | Packs | Earth observation · Media verification · People · Organisations · Infrastructure · Social · Movement (air and sea) · Regional India — one at a time, each with evals. |
| M5 | Operate | Public demo for recruiters (hosted, invite code, replays, daily caps), monitors and alerts, backups, cost and quality dashboards. |

The order is deliberate: the hardest product risk is **analysis quality**, so the engine and its evals come before breadth of sources and before the web UI.

## 7. Playbooks

| Playbook | Brief | Seed questions (abridged) | Release |
|---|---|---|---|
| `research` | An open question | What is established? What is disputed? What is unknown? | M1 |
| `verify_claim` | A claim, post or URL | Where and when did it first appear, and who published it? What do independent reliable sources say? Have fact-checkers assessed it or a close variant? Is it real material shown out of context (other time, place, event)? | M2 |
| `reconstruct_event` | Event, place, time window | What happened? When — first reports and sequence? Where exactly? Which organisations or officials were involved? Which points are disputed? | M2 |
| `org_due_diligence` | Organisation name, identifier, jurisdiction | Identity and registration; officers and owners in their professional role; sanctions and watchlists; litigation and adverse media; web presence | M4 Organisations |
| `domain_profile` | Domain, URL or IP | Registration; DNS and hosting; certificate history; reputation; related infrastructure; history | M4 Infrastructure |
| `media_verify` | Image or video | Earliest appearance; metadata and provenance (C2PA); where (geolocation); when (chronolocation); manipulation signals (signals only, never verdicts) | M4 Media |
| `movement_near_event` | Place, radius, time window | Which aircraft or vessels were present; their identities; coverage gaps | M4 Movement |
| `self_audit` | The user's own identifiers | What is public about me, where, and how to reduce exposure | M4 Social |
| `area_change` | Place (area) and two dates or a date range | What changed on the ground (flooding, burn scars, construction, damage)? When? How confident is the imagery reading? | M4 Earth observation |
| `public_figure_profile` | Name of a public figure (politician, official, executive, celebrity, journalist) | Which person exactly (disambiguation)? Public role and history; official accounts; public statements; news coverage; timeline of public activities; what others publicly say about their public role | M4 People |
| `person_lookup` | Name of an ordinary person + purpose (checking a business contact, someone who contacted you, a possible employer or landlord) | Which candidates match, kept apart with evidence and confidence; work and role; professional profiles; published work, talks, personal website; news mentions; accounts the person has publicly linked to themselves | M4 People |

`person_lookup` never: guesses accounts from a matching name, collects personal posts or photos into a file, looks for a home address, phone number, family, routine or location, matches faces, or infers protected traits (`07_SAFETY_LEGAL.md` §2–§3).

## 8. Non-goals (hard lines, enforced in code — see `07_SAFETY_LEGAL.md`)

- No access to private accounts, no credential sharing, no CAPTCHA or anti-bot bypass, no scraping where the platform's terms forbid it.
- No sock-puppet accounts and no write actions on any platform (no posts, likes, follows, messages).
- No facial recognition, face matching or biometric inference.
- No stalking-style profiling: no data brokers or breach data; no collection of a private person's personal posts or photos into a profile; no guessing of accounts from a matching name; no search for or inference of a private person's home, phone, family, contacts, routine or location. (The bounded `person_lookup` playbook in §7 is the only way ordinary people are looked up.)
- No inference of protected traits (religion, caste, ethnicity, health, sexual orientation, political opinion, trade-union membership) about any individual.
- No investigations whose subject is a minor.
- No "this is AI-generated" or "this is fake" verdicts from forensic signals alone; signals are reported as signals.
- No firehose ingestion or platform mirroring: Lantern queries on demand and on schedule.

## 9. Success measures

Quality (measured by evals, `03_AGENT_DESIGN.md` §12):

| Measure | Target |
|---|---|
| Citation precision (sentences fully supported by their cited claims) | ≥ 0.98 |
| Unsupported sentences in a published report | 0 (publication gate) |
| Planted false claims from weak sources stated as fact | 0 |
| Prompt-injection canaries followed | 0 |
| Key-question answer accuracy on eval worlds | ≥ 85% (baseline set in M2) |
| Calibration (likelihood terms vs ground truth) | tracked from M2; target set from the first baseline |

Cost and speed (`research` and `verify_claim`): on free model tiers, US$0 model cost and a median of ≤ 15 minutes per investigation (rate limits make free runs slower); on the optional low-cost tier (DeepSeek API), ≤ US$0.30 and ≤ 6 minutes (estimates in `03_AGENT_DESIGN.md` §14; real figures come from evals). Preservation: ≥ 99% of cited sources captured locally with a hash; Wayback submission attempted for ≥ 95% of cited public web pages when enabled.

Usefulness (from M3): share of findings you accept without correction, and whether Lantern actually saves you time.

## 10. Constraints that shape everything

- Personal, non-commercial project with a public demo; no commercial licences (`04_DATA_SOURCES.md` §11, `07_SAFETY_LEGAL.md` §5).
- One beginner developer directing an AI coding agent (Codex) in GitHub Codespaces; no human code review. The workflow in `05_ENGINEERING_WORKFLOW.md` substitutes for it, and the agent does the housekeeping.
- Near-zero running cost: free open-weight model tiers by default (DeepSeek's low-cost API optional), free Codespaces hours, free Oracle Cloud hosting for the demo, hard per-investigation and per-day caps.
- Every external API is treated as unstable: adapters are versioned, recorded, schema-validated and re-checked.
- The legal and ethical posture must be defensible by design, not by policy text alone.
