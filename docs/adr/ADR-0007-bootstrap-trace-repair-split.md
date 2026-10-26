# ADR 0007 — Proposed split for the remaining bootstrap trace repair

Date: 2026-10-26

Status: Proposed. No extension is active until the user approves.

Context: All three authorized joint M0 review rounds returned REQUEST_CHANGES.
The current source passes its recorded formal gate, but newly retained round-3
tests demonstrate that removed/rebound tests can still produce false requirement
coverage. The original joint review plan and review skill require stopping
after three unsuccessful rounds and proposing a split. Neither shipping nor
automatically launching a fourth review is permitted.

Proposed decision:

1. Split the remaining binding repair into the small proposed story S0.2.1
   described in PLAN-S0.2.1. Preserve all original criteria, including
   S0.2-AC3; add the two explicitly proposed repair criteria only after approval.
   The original three failure reports remain in Git history and all their
   tests remain permanent regressions.
2. Extend only the one-time bootstrap's shared story/M0-boot branch and joint
   verification to include this repair story. Do not create a normal branch
   from main that lacks the unmerged bootstrap foundation. Other stories keep
   the existing branch/session rules. Record the approved extension in the
   bootstrap/workflow notes and root branch rule before implementation.
3. Keep tests-first, implementation and full joint proof. After that proof,
   authorize exactly one additional fresh joint review, numbered 4 with the
   normal M0 prompt substitutions and all original plus repair criteria.
   This is an explicit proposed exception to the exhausted three-round budget,
   not a claim that the prior rounds approved the work. If round 4 requests
   changes, stop for another user decision; do not reset the counter again.
4. Only APPROVE followed by final proof including the new review tests may
   lead to a later shipping proposal. This decision does not authorize a PR,
   merge, new key, paid service, account setting or protected harness change.
   All existing quality thresholds and the 800-line combined counting bound
   remain required.

Alternative: stop the bootstrap with the current known failure and leave it
unmerged. A general rewrite of pytest discovery is unnecessary for the
demonstrated binding defect and is outside the proposed repair.

References: PLAN-M0; PLAN-S0.2.1; docs/05 §4; docs/08 §5;
.agents/skills/review/SKILL.md step 9; ADR 0003.
