# Lantern — START HERE

Pack 3.0 · written 2026-10-22. External facts (model providers and free limits, API terms, quotas, library versions, legal dates) were checked in October 2026 and will drift; every story re-checks what it depends on.

## What Lantern is

Lantern is an **open-source intelligence (OSINT) investigation platform**: it investigates questions using only **publicly available information**: the web, news, social media posts, satellite images, aircraft and ship tracking data, and company and domain records.

You type a question. Lantern's AI does the research the way a careful analyst would:

1. It splits the question into **key questions**.
2. It gathers public evidence through audited tools, and **saves a copy** of every source it uses.
3. It pulls out **claims tied to exact quotes**.
4. It counts only **independent** sources as corroboration.
5. It rates each answer in **standard analytic language** (Admiralty source ratings, ICD 203 likelihood words, rule-based confidence).
6. It publishes a report only after **every sentence has been checked** against the evidence it cites. Click any citation to see the exact quote in the saved copy.

Examples of what you can ask:
- *"Floods in eastern Nepal, 20–25 September 2026: what happened, where, and how bad?"* → timeline, satellite before/after, rainfall, relief flights, casualty figures with who reported them.
- *"Is this viral video really from Guwahati yesterday?"* → earliest copy, fact-checks, verdict with proof.
- *"Which aircraft circled this area on Tuesday afternoon?"*
- *"Who runs this company, and is it on any sanctions list?"*
- *"Who is this minister, and what has she said about the dam project?"* (public figures)
- *"Is the person who emailed me really a manager at this firm?"* (a bounded professional lookup, never stalking)

**Guardrails are part of the architecture**: purpose checks, public data only, no face recognition, no stalking-style profiling, minors protected, prompt-injection containment.

It is a personal, non-commercial project with a **public demo** for recruiters, built in a **public GitHub repository** by an AI coding agent (**Codex**) inside **GitHub Codespaces**, running on **free open-weight AI models**.

## This folder

| # | File | What it is |
|---|---|---|
| — | `AGENTS.md` | the rules the coding agent loads in every session |
| 0 | `docs/00_START_HERE.md` | this page |
| 1 | `docs/01_PRODUCT_SPEC.md` | vision, concepts, examples, releases, playbooks, non-goals, success measures |
| 2 | `docs/02_SYSTEM_DESIGN.md` | architecture, data model, flows, egress, preservation, model gateway, durable runs, budgets, events, security, deployment, stack |
| 3 | `docs/03_AGENT_DESIGN.md` | the investigation loop, roles, context, extraction, assessment standard, people rules, ACH, report verification, evals, cost and quota |
| 4 | `docs/04_DATA_SOURCES.md` | model providers and every data source, with terms, limits and prices as checked |
| 5 | `docs/05_ENGINEERING_WORKFLOW.md` | the build loop, definition of done, tooling config, Codex setup, the review prompt, tests, CI |
| 6 | `docs/06_ROADMAP_BACKLOG.md` | milestones and stories with acceptance-criteria IDs: what to build, in order |
| 7 | `docs/07_SAFETY_LEGAL.md` | invariants with enforcement and proof, purposes and subjects, policy gate, data protection, retention, demo rules |
| 8 | `docs/08_SETUP.md` | step-by-step setup in Codespaces, the one-time M0 bootstrap, daily routine, API keys |
| 9 | `docs/09_DECISIONS.md` | every major decision with alternatives and reasons |
| — | `.agents/skills/` | the agent's skills: `$plan`, `$tests-first`, `$implement`, `$prove`, `$review`, `$ship`, `$smoke`, `$plan-epic`, `$security-audit`, `$test-audit` |
| — | `.codex/` | Codex settings, command rules and the review prompt |
| — | `.devcontainer/` | the Codespace definition (Python, uv, Docker, Node, Codex) |
| — | `scripts/review_schema.json` | the format of the independent review's result (used from the first review) |

## How to start

Follow `docs/08_SETUP.md`:
1. Create a public `lantern` repository and open a codespace.
2. Unpack this pack into it, and rebuild the container.
3. Sign in to Codex and trust the project.
4. Paste the first prompt.

After that, the agent proposes each step and waits for your yes.

## The plan in one table

| Milestone | You get |
|---|---|
| M0 Foundation | tooling, proof, guards, review and CI kits; the workflow running |
| M1 Walking skeleton | `lantern run "<question>"` → a cited report, replayable, measured by evals |
| M2 Trustworthy core | durable runs, policy gate, independence, assessment standard, competing hypotheses, verification gate, preservation, news and fact-checks, evidence bundle |
| M3 Workspace | the web app: briefs, live runs, approvals, reports with clickable citations, evidence review, timeline and map |
| M4 Packs | Earth observation · media verification · people · aircraft and ships · organisations · infrastructure · social · regional India |
| M5 Operate | public demo for recruiters, monitors and alerts, backups, dashboards |

This is the whole product, not just an MVP. M1 is simply the first point where it works end to end.

## Facts checked in October 2026 that shaped the design

**Models and tools**
- Free open-model tiers limit **tokens per day**. Groq's free gpt-oss-120b allows about 200,000 tokens a day, and an investigation uses several hundred thousand. So, combining free providers, expect **about 2–4 live investigations a day**.
  - Development and CI run on recorded replays, which cost nothing.
  - DeepSeek's API (about $0.15–0.30 per investigation) is the optional upgrade (`03` §14).
- Codex reads `AGENTS.md` and skills in `.agents/skills/`. It enforces project settings, command rules and hooks from `.codex/` once the project is trusted. `codex exec` gives the fresh, independent review session.

**Data-source terms**
- Brave's and Exa's terms forbid storing search results, so results stay transient (`02` §8.1). Tavily's free tier is the default search.
- Bluesky post search mostly needs an authenticated account.
- Reddit needs approval for any API use.
- X's terms forbid "investigating or tracking" users.
- Telegram's terms forbid scraping and AI use.
- Social scope is narrowed accordingly (`04` §4).

**Standards and hosting**
- ICD 203 forbids putting a likelihood term and a confidence level in the same sentence. The report language follows that rule.
- Oracle Cloud's Always Free ARM allowance is now 2 cores and 12 GB, enough for the demo. Idle instances can be reclaimed, which the demo runbook handles.

## Decisions not to re-open inside a session

They are recorded in `09_DECISIONS.md`. The agent may point out a problem and propose a decision record; it may not silently diverge.
