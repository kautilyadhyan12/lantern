---
name: test-audit
description: Advisory, read-only audit of the current story's tests for vacuous assertions, missing properties and missing negative cases. Use before $prove on non-trivial stories; it never replaces $review. Invoke as "$test-audit <story-id>".
---
Do not modify any file. Read the PLAN (docs/plans/PLAN-<ID>.md), the tests marked with that story's AC IDs, and the code they exercise.

Check each test for:
1. Real behaviour, not mocks: a test that only asserts on a mock's calls, or mocks the unit under test, is vacuous.
2. Tests that cannot fail: tautologies, assertions on constants, duplicated tests, assertions only on types.
3. Missing property tests: every pure function in the PLAN's Design section needs at least one hypothesis property (idempotence, monotonicity, bounds, round-trip, order-independence — whichever applies).
4. Missing negative and boundary cases: empty, None, oversized, Unicode and right-to-left text, naive datetimes, malformed payloads, 429/5xx/timeouts, quota exhaustion, repeated execution.
5. Contract tests that do not use recorded cassettes, or cassettes without a provenance header.
6. AC coverage: each AC has a test that would fail if the AC were not met.

Output: vacuous tests, missing properties, missing cases, cassette issues, notes — each with file::test name. Plain words.
