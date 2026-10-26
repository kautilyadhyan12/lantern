# ADR 0004 — Bind bootstrap reviews to code without editing generated artifacts

Date: 2026-10-23

Status: Accepted 2026-10-26. The user instructed "continue lantern from plan M0",
approving the saved plan and its explicitly included metadata clarification.

Context: docs/05 §4.1 requires validating the review payload against the shipped
schema and adding a code_tree digest. Its pre-S0.4 exception permits only
codex exec --output-last-message to write the review artifact. The shipped
schema has additionalProperties=false and no code_tree property. Writing the
raw review and adding the digest by hand would violate the artifact rule;
changing the shipped schema would violate S0.1-AC6. Neither is authorized here.

Decision: During the pre-S0.4 manual bootstrap only, create a temporary
output schema outside the repository by copying the shipped schema in memory
and adding exactly one required property: code_tree, a string with a one-value
enum containing the digest computed by scripts/code_tree.py for the captured
commit, excluding docs/ and tests/review/. Do not modify the shipped schema or
the T3 prompt. Show the complete reviewer command before running it. Use the
temporary schema as --output-schema and the repository's review artifact as
--output-last-message. The fresh reviewer CLI remains the sole artifact writer.

Afterward, validate a separate in-memory payload with only code_tree removed
against the unchanged shipped schema; validate the digest separately against
the captured code, and validate head_sha against the reviewed HEAD. Reject any
unexpected key, incorrect digest, wrong HEAD, invalid payload or missing test
file. Never repair or rewrite the review artifact. Its verdict, findings and
adversarial tests must come from the independent reviewer.

This reproduces the normal workflow's payload-validation/metadata distinction
while respecting the manual writer exception. It is not permission to bypass
review, modify a verdict, hand-author an artifact, change the harness, or build
the S0.4 review runner early. S0.4 will implement the normal validated writer.

The explanatory note in docs/05 §4.2 records this procedure. The shipped schema,
prompt and generated artifacts remain protected from hand edits.

References: D12; docs/05 §4.1–§4.2; docs/08 §5; scripts/review_schema.json;
AGENTS.md Asking first §3; .agents/skills/review/SKILL.md §4.
