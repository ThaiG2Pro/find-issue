# Glossary — v2-006-discussions (ticket V2-006)

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| Discussion | A GitHub Discussions thread (RFC / Q&A / announcement / idea) for a repo, collected as a `RawItem` with `item_type = "discussion"` | analyst | AC-V2-006-001 | S2 |
| Approach A (inclusion rule) | Discussions are included when their `createdAt` is within `lookback_days` — the same "newly-created" rule as issues; NOT activity/hotness-based | analyst | BR-V2-006-002 | S2 |
| GraphQL transport | The discussion path issues one `POST` to the `/graphql` endpoint (derived from `base_url`) with a fixed query+variables body — the sole exception to the collector's REST GET-only rule | analyst | BR-V2-006-005, BR-V2-006-006 | S2 |
| Cursor pagination | GraphQL page-walking via `pageInfo.hasNextPage` + `pageInfo.endCursor`, replacing the REST `Link` header on this path; bounded by the same `max_items_per_repo`/`page_size` | analyst | AC-V2-006-011 | S2 |
| 200-with-errors model | A GraphQL `200 OK` can still carry a top-level `errors` array; a `null` `discussions` connection + errors means Discussions disabled/repo-not-found → skip repo; other errors → raise | analyst | BR-V2-006-007, AC-V2-006-003, AC-V2-006-014 | S2 |
| Discussions disabled | A repo where the Discussions feature is off — surfaced as `data.repository.discussions == null` + errors; treated as a graceful skip (WARN + empty list), same outcome as a 404 repo on REST | analyst | AC-V2-006-003, BR-V2-006-007 | S2 |
| Discussion identity | State-store/delta key `repo + "discussion" + number` (per-repo discussion number, stringified); reuses the item_type-agnostic key contract | analyst | BR-V2-006-001 | S2 |
| fetch_discussions | Adapter-only method `fetch_discussions(repo, lookback_days) -> list[RawItem]`; the frozen `GitHubClient` Protocol is NOT extended (mirrors v2-003 `fetch_releases`) | analyst | BR-V2-006-003, AC-V2-006-018 | S2 |
| `_classify_graphql` | Architect S3 helper: shape-first ordered classification of a GraphQL 200 payload — null `repository`/`discussions` → skip repo; else non-empty top-level `errors` → raise; else return the connection. The single RISK-003 decision point | architect | AC-V2-006-003, AC-V2-006-014 | S3 |
| `json_body` transport switch | Architect S3 (ADR-002): keyword param on `_request_with_retry` — `None` → GET (REST callers unchanged), a dict → POST (GraphQL only). Scopes GET-only to REST, adds one fixed POST for GraphQL, sharing one retry/classify path | architect | AC-V2-006-015, AC-V2-006-016 | S3 |
| `_DISCUSSIONS_QUERY` | Architect S3 (ADR-004): the fixed, hardcoded, non-mutating GraphQL query constant selecting `number title body url createdAt` + `pageInfo`, ordered `CREATED_AT DESC`; only owner/name/first/after are variables | architect | AC-V2-006-016 | S3 |
| Shape-first classification | Architect S3 (ADR-003): detect disabled Discussions by the null connection SHAPE (not a hardcoded `errors[].type` string), so it is robust to GitHub's error wording; the null-shape check precedes the errors-raise check | architect | AC-V2-006-003 | S3 |
