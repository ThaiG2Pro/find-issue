# Memory — analyst — v2-006-discussions

## 2026-07-09 — v2-006-discussions: a GraphQL source breaks 3 REST assumptions the "just add a source" ask hides
Adding GitHub Discussions looked identical to v2-003 releases ("teach the collector one more
`fetch_*`, wire one call, reuse everything"), but Discussions is GraphQL-only and silently violates
three invariants baked into the REST collector — each needs its own AC the raw requirement never
mentions:
1. **Transport verb**: GraphQL is `POST` (with a query+variables body), not the collector's GET-only
   rule → scope "GET-only" to the REST paths + add "POST fixed non-mutating query only" (AC-V2-006-016/017).
2. **Pagination**: GraphQL uses cursors (`pageInfo.hasNextPage`/`endCursor`), not the REST `Link`
   header → the early-stop loop must be re-expressed over cursors (AC-V2-006-011/012).
3. **Error model**: a GraphQL `200 OK` can carry a top-level `errors` array and a `null` connection
   (Discussions disabled / repo not found). Treating every 200 as success (the REST assumption) either
   crashes on a null-deref or silently drops a repo. This is the highest-risk area — spec THREE
   outcomes from one 200: map / skip-repo-gracefully / raise (AC-V2-006-003/014, RISK-003 MEDIUM).
Also: when inclusion and ordering key on the SAME field (`createdAt` here), the v2-003 RISK-002
ordering-vs-inclusion skew does NOT recur — Approach A is genuinely simpler than releases on that axis.
Renderer/state/delta/config all stayed unchanged (item_type-agnostic pipeline) — same "no no-op
renderer delta" call as v2-003.
