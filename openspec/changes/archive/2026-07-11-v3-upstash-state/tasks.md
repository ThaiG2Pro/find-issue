# Tasks: V3-003 — `v3-upstash-state`

> Scope: tiny · one new adapter + env-driven backend selection · no Protocol change.

- [x] 1. Add the `upstash-redis` dependency (pinned) to `pyproject.toml`.
  _Requirements: AC-V3-003-001_

- [x] 2. Implement `UpstashStateStore` (`src/osspulse/state/upstash_store.py`): `load`/`save`
  (Protocol) + `is_seen`/`mark_seen` helpers with semantics identical to `JsonFileStateStore`
  (write-once `first_seen_at` via `HSETNX`, empty-list no-op, `repo+item_type+item_id` identity).
  Key `osspulse:state:{repo}`, field `{item_type}:{item_id}`, value `first_seen_at`.
  Reads REST URL/token from env; never logs them.
  _Requirements: AC-V3-003-001, AC-V3-003-002, AC-V3-003-003, AC-V3-003-006, AC-V3-003-008_

- [x] 3. Map Upstash runtime failures to `StateError` (fail loud — no silent fallback / empty state).
  _Requirements: AC-V3-003-007_

- [x] 4. Add `pipeline._build_store()`: both `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN`
  present → `UpstashStateStore`, else `JsonFileStateStore(config.state_path)`. Wire it into
  `run_pipeline` in place of the direct `JsonFileStateStore(...)` construction.
  _Requirements: AC-V3-003-004, AC-V3-003-005_

- [x] 5. Widen the `state` type hint on `_partition_new` / `_collect_all` to the shared seen-tracker
  type (or a `SeenTracker` Protocol added to `ports.py` — does NOT change `StateStore`), so both
  backends are accepted. Behavior unchanged.
  _Requirements: AC-V3-003-008_

- [x] 6. Document the two Upstash secrets (`UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`)
  in README + `.env.example`, noting env-var presence selects the backend and absence keeps the
  local JSON file.
  _Requirements: AC-V3-003-004, AC-V3-003-005, AC-V3-003-006_

- [x] 7. **CHECKPOINT (final)**: module-scope tests + lint/static-analysis for `state/` + `pipeline`
  green; `StateStore` Protocol unchanged; both backends round-trip `is_seen`/`mark_seen`
  (Upstash mocked — no live network in tests); no secret substring in code/logs; AC-V3-003-001..008 verified.
  _Requirements: AC-V3-003-001, AC-V3-003-002, AC-V3-003-003, AC-V3-003-004, AC-V3-003-005, AC-V3-003-006, AC-V3-003-007, AC-V3-003-008_
