# 07 — Safety, Privacy and Legal Controls

Pack 3.0 · written 2026-10-22 · status: source of truth for engineering controls

**This is not legal advice.** It records what the software enforces so the product is defensible by design. Lantern is a personal tool; if it is ever offered to others, a lawyer must first review the items in §11.

## 1. Non-negotiable invariants

Each invariant has an enforcement point in code and a test that proves it. Violating any of them is a review blocker.

| # | Invariant | Enforced by | Proven by |
|---|---|---|---|
| 1 | Public data through official APIs or permitted access only: no private accounts, no credential sharing, no CAPTCHA or anti-bot bypass, no scraping where terms forbid it | adapter checklist (04 §12); licence metadata per tool; SafeTransport has no cookie jar or login flow; no headless-browser automation of platforms | adapter contract tests; review checklist |
| 2 | No sock puppets and no write actions on any platform | every tool declares `side_effects = "none"`; the registry rejects any other value; the only accounts used are the user's own, read-only, where an official API requires login | registry test |
| 3 | No facial recognition, face matching or biometric inference | no such tools; a dependency deny-list check in `make check` (face-recognition and face-embedding libraries) | dependency scan test |
| 4 | No stalking-style profiling: no data brokers or breach data; ordinary people only through `person_lookup` under §2.2; never a private person's home, phone, family, contacts, routine or location | source deny-list; gatekeeper; output post-check for addresses and contact details of private people; prompt rules | policy tests; eval cases |
| 5 | No inference of protected traits (religion, caste, ethnicity, health, sexual orientation, political opinion, trade-union membership) about any individual | shared prompt rules; extraction screen; report screen | table tests incl. non-English; eval cases |
| 6 | No investigation whose subject is a minor | pre-rules; gatekeeper `likely_minor`; post-check indicators stop work on that subject | policy tests; eval cases |
| 7 | Every fetch is SSRF-safe, identifies itself, respects robots.txt for generic web pages and obeys per-source rate limits and licences | SafeTransport, robots cache, limiters | egress tests |
| 8 | Every used source is preserved with its sha256; every tool call, model call and policy decision is in the hash-chained event log | capture pipeline; repositories write events in the same transaction | ledger tests; golden run verifies its chain |
| 9 | Reports never state uncorroborated claims as fact; allegations are always attributed; the verification gate decides publication | assessment rules; language lint; verifier; publish gate | assessment tests; trap eval cases |
| 10 | Retention is bounded and deletion is real | retention job; deletion receipts | deletion tests |
| 11 | Captured content cannot cause actions outside policy (prompt-injection containment) | untrusted-content wrapping; read-only tools; URL provenance; vetting of every proposed action | injection-canary eval cases; gateway tests |
| 12 | Demo visitors never get `person_lookup` or `self_audit` and never exceed the demo caps | demo-mode allow-list and caps in the API and runner | demo-mode tests (O-DEMO) |

## 2. Purposes and subjects

The user declares a purpose for every investigation. The gatekeeper classifies the subjects of the brief. The table decides what is allowed.

| Subject ↓ / Purpose → | journalism | research | due_diligence | security_research | professional_lookup | self_audit | other_lawful |
|---|---|---|---|---|---|---|---|
| Organisation, place, event, infrastructure | allowed | allowed | allowed | allowed | denied (use another purpose) | denied (use another purpose) | allowed |
| Public figure, in their public role | allowed (public-role conduct only) | allowed (public role) | allowed (professional capacity) | restricted | allowed (`person_lookup` rules) | denied (use another purpose) | restricted |
| Named private individual | restricted: only as author or subject of specific public content under investigation, and only that content | denied as a named subject (aggregate studies only) | restricted: professional capacity only (registries, sanctions, adverse media) | restricted: persona/account level only, no linking to a real identity | allowed only through `person_lookup` (§2.2) | allowed only for the user's own identifiers, with ownership attested | denied |
| Online account or persona | restricted: its public content | restricted | restricted | allowed at persona level | denied | own accounts only | restricted |
| Anyone likely under 18 | **denied** | **denied** | **denied** | **denied** | **denied** | **denied** | **denied** |

Any named person as a subject — public figure or private individual — requires attestation before the run (§3.3). "Restricted" additionally means: the person-pivot rule applies (§3.5) and the playbook's tools are narrowed by the listed restrictions.

### 2.1 Public figures (`public_figure_profile`)

A public figure is someone with a public role: elected officials and candidates, government officials, executives and board members of organisations, celebrities, journalists, public commentators. The playbook covers their public role only: official accounts, public statements, news coverage, public activities and what others publicly say about that role. The public role must be shown by **evidence captured by code** — an official site (government, parliament, party, organisation) or a Wikidata entry with a position held — before any other research starts. Without it, `public_figure_profile` is **denied** (not restricted), and the user may choose `person_lookup` instead, outside demo mode.

### 2.2 Ordinary people (`person_lookup`, purpose `professional_lookup`)

Allowed purposes, one of which the user must state: checking a business contact or potential partner; checking someone who contacted the user; checking a possible employer, client or service provider; verifying that a person who claims a role really holds it.

Lantern may show: candidates that match the name, kept apart with the anchors that distinguish them (`03_AGENT_DESIGN.md` §8.8); work and role; professional profiles linked from captured pages; published work, talks, personal website; news mentions attached through anchors; accounts the person has publicly linked to themselves.

Lantern never: guesses accounts from a matching name, username or photo; collects personal posts or photos into a file; searches for or infers a home address, phone number, personal email, family, relatives, contacts, routine or location; matches faces; infers protected traits; continues if the person may be under 18.

Person lookups are kept for 30 days by default (§6) and are never available to demo visitors (§2.3).

### 2.3 Demo visitors (M5 public demo)

Visitors to the public demo may replay recorded investigations and run live ones only with these playbooks: `research`, `verify_claim`, `reconstruct_event`, `area_change`, `domain_profile`, `org_due_diligence`, `public_figure_profile`. They never get `person_lookup` or `self_audit`, and every visitor brief still passes the full policy gate. Visitor investigations are deleted after 7 days. In demo mode, any brief whose subject is a named private individual is denied whatever the purpose. Default caps: 3 live investigations per visitor code per day, 10 in total per day, and US$1 per day on paid models (configurable). The owner's own account has the full product.

## 3. The policy gate

### 3.1 Deterministic pre-rules (before any model call)

Deny with a stated reason when the objective, in any supported language, seeks to: locate or track a person (home, address, whereabouts, daily routine, live location); monitor a partner, former partner, family member, colleague or neighbour; unmask an anonymous account outside security research into threat actors; obtain private data (passwords, private messages, medical, financial or identity documents); harass, intimidate, shame or dox anyone; or evade law enforcement. Pattern lists live in `src/lantern/policy/rules.yaml` with tests for each pattern and for near-miss phrasings that must not trigger.

### 3.2 Gatekeeper (model, fast tier)

Returns `{outcome, reasons[], subjects[{name, type, public_role_evidence}], named_private_person, likely_minor, restrictions[]}`. The final decision is the **strictest** of the pre-rules and the gatekeeper, computed by a pure function. `likely_minor = true` always denies.

Outcomes: `allow` · `allow_with_restrictions` · `needs_attestation` · `deny`. Every decision is an event; the report's appendix shows it.

### 3.3 Attestation

Required whenever a named person (public figure or private individual) is a subject. It is recorded once, before any run, and is not an in-run approval. The user affirms: the stated purpose is genuine and lawful; the investigation serves a public or legitimate interest; the output will not be used to harass, intimidate or discriminate; for `self_audit`, the identifiers belong to the user. Stored as an event with the user and time.

### 3.4 Restrictions

Persisted with the decision and enforced by the tool gateway, for example: no social-account pivots; registry, sanctions and adverse-media tools only; no username checks; no person-name searches outside the listed sources.

### 3.5 Person-pivot rule (at run time)

When the researcher proposes a tool call that targets a person not cleared by the brief's decision, the gateway refuses it unless the evidence already captured shows that person is a public figure acting in a public role relevant to the question. Refusals are events and are shown to the researcher and in the report's method section.

### 3.6 Output post-checks

Claims (at extraction) and report sentences (before verification) are screened for protected-trait attributions, private addresses or contact details, and minor indicators. Offending claims are dropped; offending sentences are removed and listed. A minor indicator stops all work on that subject and flags the investigation for the user.

## 4. Platform and source obligations

Encoded in each adapter's `licence` metadata and enforced by the gateway or background jobs (details and URLs in `04_DATA_SOURCES.md`):

- **Search APIs**: results are transient — never stored or cached (02 §8.1).
- **Bluesky**: the user's own account only; honour `!no-unauthenticated` and moderation labels.
- **Mastodon**: honour `discoverable: false`, `noindex` and instance rules.
- **YouTube**: Data API only; non-authorised data cached at most 30 days; no transcript scraping.
- **Reddit**: only after written API approval; purge deleted content; no inference of sensitive traits.
- **X**: content search only, never user-centric; delete within 24 hours where required; approval-gated.
- **Telegram, Instagram, Facebook, LinkedIn, TikTok, Threads**: no automated collection; manual ingest only.
- **OpenStreetMap services**: User-Agent, 1 request/s, no bulk; attribution (ODbL).
- **Non-commercial sources** (OpenSky, airplanes.live, adsb.fi, Global Fishing Watch, Open-Meteo free, VirusTotal public, OpenSanctions bulk, OpenCorporates free keys): flagged `commercial_ok = false`.
- **Generic web**: robots.txt, User-Agent with contact, size and time caps, no login walls.

## 5. Data protection

### 5.1 India — Digital Personal Data Protection Act 2023 and Rules 2025

- The Act's commencement provisions and the DPDP Rules 2025 were notified on **13 November 2025**. Provisions on the Data Protection Board applied at once; consent-manager rules apply from **13 November 2026**; most obligations — notice, security safeguards, breach notification, erasure, children's data, data-principal rights, cross-border rules — apply from **13 May 2027**. (Board members were not yet appointed as of an August 2026 parliamentary answer; check the current position.)
- The Act does **not** apply to personal data made publicly available by the person it relates to, or by someone legally obliged to publish it (s.3(c)(ii)). Data that is merely public — posted by third parties, leaked, scraped — is **not** covered by that exception. Much of what Lantern captures about people is therefore in scope.
- Unlike earlier drafts, the 2023 Act has no general exemption for journalism. Do not rely on any exemption without legal advice.
- **Personal use.** The Act also does not apply to personal data "processed by an individual for any personal or domestic purpose" (s.3(c)(i)). Using Lantern privately, for your own curiosity or safety, plausibly falls under that. The public demo is not purely personal (other people run investigations), which is one reason visitors get no person lookups and a 7-day retention. Researching other people for work, for publication or on someone else's behalf may not — so the engineering response below is built in anyway, and it is good practice regardless.
- **Engineering response (built in, whatever the legal position)**: purpose limitation (the purpose gate); data minimisation (subject rules, narrow capture of personal data, no special categories); reasonable security safeguards (02 §17); bounded retention and real deletion (§6). A privacy notice, breach runbook and grievance contact only matter if Lantern is ever offered to others (§11).

### 5.2 EU and UK (when users or subjects are there)

Legitimate-interest assessment for OSINT processing; data-subject requests (access, erasure) handled by an identifier search across claims, entities and sources with export or deletion; records of processing. Journalistic exemptions differ by country and need advice.

### 5.3 Data-subject requests

Useful even for personal use, as part of real deletion (a small story, schedule when wanted): `lantern privacy find --identifier <value>` lists every source, claim and entity matching a name, handle, email or phone; the operator can export or delete the matches; each action is an event.

## 6. Retention and deletion

- Default retention: **180 days after an investigation completes** (investigations often resurface months later, and the period is still bounded). The user may shorten it, extend it up to 2 years, or set a hold with a written reason; holds are events.
- Shorter defaults: person lookups (`person_lookup`, `public_figure_profile`) **30 days**; demo visitor investigations **7 days**. When two limits apply, the shorter wins.
- Source-specific limits from terms override the default (for example YouTube data from non-authorised users: 30 days).
- Deletion removes, in one database transaction, all of the investigation's rows (its event chain included) and appends a receipt to the system event chain; blobs and WARC files no other investigation references are removed next, with retries. It runs through a maintenance-role function, never as the application role (02 §14).
- Exports are the user's responsibility once downloaded; the export screen says so.

## 7. Other law (India first; other jurisdictions as relevant)

- **Unauthorised access**: the IT Act 2000 s.43 creates liability for accessing a computer system without permission; s.66 makes doing so dishonestly or fraudulently an offence (up to three years and/or a ₹5 lakh fine). Invariant 1 is the implementation. Similar laws elsewhere (US CFAA, UK Computer Misuse Act).
- **Defamation**: criminal defamation is s.356 of the Bharatiya Nyaya Sanhita 2023 (in force 1 July 2024, replacing IPC s.499–500); civil liability is separate. The assessment standard, attributed allegations, the verification gate and the rule that reports are drafts for a human editor (§9) are the engineering response.
- **Copyright**: preserved copies are kept as evidence for internal analysis; reports quote briefly; full captured pages are exported only to the investigation's owner, never republished by Lantern. Fair-dealing limits (India Copyright Act s.52) need counsel's confirmation for the product's uses.
- **Platform terms** are contracts: breaching them risks bans and claims. §4 encodes them.

## 8. Guardrails for the owner and the demo

The guardrails protect the people being researched and keep the tool honest:
- The purpose gate, person-pivot rule and post-checks run on every investigation, including yours; they are not switched off for personal use.
- A soft cap on investigations with person subjects (default 10 per day) asks you to confirm before going further.
- A kill switch per adapter (configuration) and a global read-only mode.
- Public demo (§2.3): invite codes, a playbook allow-list, per-visitor and global daily caps, rate-limited login, 7-day retention, and the owner can revoke codes. Repeated policy denials from one visitor code disable that code.

## 9. Transparency in every report

Every report ends with: the policy decision and any attestation; sources with ratings, origin clusters and archive status; licences and required attributions; what was not checked and why (budget, policy, unavailable sources, unanswerable questions); spend; a statement that the analysis was produced with automated assistance and must be reviewed by a responsible person before publication or action.

## 10. Security controls

See `02_SYSTEM_DESIGN.md` §17 (threat model) and §9 (egress). Highlights: SSRF-safe transport; prompt-injection containment; secrets only in the environment; captured HTML never rendered in the app origin; hash-chained events with a database role that cannot rewrite them; dependency audits.

## 11. Only if Lantern is ever offered to others (lawyer review first)

Not planned. Personal use needs none of this; it is listed so the path is clear.

1. Privacy notice, lawful basis and data-processing records (DPDP, and GDPR where relevant).
2. Terms of use and acceptable-use policy matching §2–§3.
3. Licences for every enabled data source in commercial mode (04 §11).
4. Defamation and editorial-review process for users who publish.
5. Breach-response runbook and grievance officer.
6. Copyright position on preservation and exports.
7. Cross-border transfer position for hosting location and model API usage.
