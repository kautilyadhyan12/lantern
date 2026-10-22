---
name: smoke
description: Run the milestone's smoke check on main after a merge and report the result. Invoke as "$smoke".
---
1. Be on an up-to-date `main` with a clean tree.
2. If `make smoke` does not exist yet (it arrives with S1.12), run `make check` instead and say so.
3. Otherwise run `make smoke`. From M1 it replays a full investigation offline and renders the report; from M2 it also kills and restarts a worker mid-run; from M3 it drives an investigation through the HTTP API on the compose stack.
4. Report pass or fail in plain English. If it fails, do not fix on `main`: propose a FIX story with the failing output and stop.
