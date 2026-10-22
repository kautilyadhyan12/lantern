---
name: security-audit
description: Advisory, read-only security and policy checklist for the current story's diff. Use before $prove on stories touching egress, tools, policy, people, capture, rendering, the demo or retention. Never replaces $review. Invoke as "$security-audit <story-id>".
---
Do not modify any file. Read docs/02_SYSTEM_DESIGN.md §9 and §17, docs/07_SAFETY_LEGAL.md §1–§2, the story's PLAN and `git diff main...HEAD`.

Check, with file:line evidence:
1. SSRF: all outbound HTTP through SafeTransport; private, loopback, link-local, CGNAT, multicast, reserved and metadata addresses blocked after resolution, including IPv6 and odd IPv4 spellings; connections pinned; every redirect re-validated; size and time caps.
2. Prompt injection: captured text only inside evidence wrappers; no captured content can trigger a tool call outside vetting; the fetch tool accepts only known URLs; tools have no side effects.
3. Secrets: none in code, cassettes, logs, events, prompts or exception messages; settings use SecretStr; log redaction applied; nothing secret in a public file.
4. People: protected-trait screen; no private addresses, phones or contacts stored or logged; account attribution only through the rules of docs/03 §8.8; minors handling intact; demo visitors cannot reach `person_lookup` or `self_audit`.
5. Files and processes: blob paths derived only from hashes; no path traversal; subprocesses with argument lists only; limits on parsing untrusted files.
6. Rendering: evidence text escaped in HTML; captured HTML never rendered in the app origin.
7. Data: SQL only through SQLAlchemy with bound parameters; events written in the same transaction; no UPDATE or DELETE on events except through the deletion function.
8. Platform terms and quotas: storage and caching rights respected (search results transient); rate limits and attribution per docs/04; free-quota and demo caps enforced.
9. Cost: no unbounded loops or retries; every paid call reserved against the budget first.

Output: a short list of blockers (area, file:line, why, a pytest that would fail today), then warnings, then notes. Plain words.
