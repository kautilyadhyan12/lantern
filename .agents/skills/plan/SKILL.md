---
name: plan
description: Write docs/plans/PLAN-<ID>.md for one backlog story, then stop for the user's approval. Use before any tests or code for a story. Invoke as "$plan <story-id>".
---
The story ID is the text the user typed after `$plan` (for example `S1.3`).

1. Read AGENTS.md, docs/05_ENGINEERING_WORKFLOW.md (the loop and the PLAN format), the story in docs/06_ROADMAP_BACKLOG.md, every design section it references (docs/02, docs/03, docs/07) and the docs/04 rows for any external source or model provider it uses. If the ID is an epic (P-… or O-…), stop and use `$plan-epic` instead.
2. Branch: create `story/<ID>` from an up-to-date `main` (for S0.1 and S0.2: the shared branch `story/M0-boot`, docs/08_SETUP.md §5). Never work on `main`.
3. Re-verify every external fact the story depends on with web search: prices, free-tier limits, authentication, rate limits, terms (commercial use, storage and caching rights, restricted uses), library versions and licences. Record what you checked, with URLs and today's date.
4. Write docs/plans/PLAN-<ID>.md with exactly these sections:
   - `# PLAN <ID> — <title>`
   - `## Goal` — one paragraph, plain English.
   - `## Scope` — in / out.
   - `## Design` — interfaces with full signatures (Pydantic models, functions, classes), data and migrations, files to touch, and the layer each new module belongs to (docs/02 §5).
   - `## Acceptance criteria` — copied verbatim from the backlog; add none, change none. If one seems wrong, add a "Proposed AC changes" subsection and STOP for the user.
   - `## Test plan` — for each AC: test file, test names, kind (unit, property, contract, e2e); cassettes to record; eval cases if agent behaviour changes.
   - `## External facts checked` — with URLs and date, or "none".
   - `## Risks and mitigations` — security (SSRF, injection, secrets, file paths), privacy, platform terms, cost and quota.
   - `## Size` — non-test LOC estimate; if above 400, propose a split and STOP.
   - `## Rollback`
   - `## Log` — start with "Plan written <date>".
5. Do not write tests or src/ code in this step.
6. Commit the PLAN and push the branch (`git push -u origin HEAD`; docs/05 §1.1).
7. Post a short plain-English summary in the chat: what gets built, what does not, the size, anything risky or uncertain, and any question for the user. Then stop and wait for a yes.
