---
name: plan-epic
description: Break an M4 or M5 epic (P-… or O-…) into backlog stories with acceptance criteria, for the user's approval. Invoke as "$plan-epic <epic-id>".
---
The epic ID is the text the user typed after `$plan-epic` (for example `P-EARTH`).

1. Read AGENTS.md, the epic's row in docs/06_ROADMAP_BACKLOG.md, the docs/04 rows for its sources, docs/07 for policy implications and docs/03 for agent changes.
2. Re-verify every source the epic needs with web search: prices, free limits, authentication, terms (commercial use, storage and caching rights, restricted uses such as surveillance or profiling). Note anything that blocks the epic (approvals, application forms, costs, terms).
3. Propose 4–10 stories in dependency order, each at most ~400 non-test lines, with IDs `<epic>.1`, `<epic>.2`, … For each: title, size (S/M/L), refs, and 2–6 testable acceptance criteria written like the existing ones (`<story>-AC<n> …`). Cover: adapters with cassette contract tests, policy-rule updates, the pack's playbook(s), at least 5 eval cases, licence and attribution handling, demo-mode rules, and any retention limits from the sources' terms.
4. Post the proposal and the verified facts (with URLs) in the chat and STOP.
5. Only after the user approves: append the stories under the epic in docs/06_ROADMAP_BACKLOG.md, update the docs/04 rows you re-verified (with today's date), commit and push.
