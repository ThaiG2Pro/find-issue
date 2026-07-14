## 2026-07-14 — discord-retry: shared retry helper pattern for multi-path adapters

When an adapter has two methods that share the same POST → classify → backoff → raise
pattern (e.g. plain-text and embed paths both calling the same endpoint), extract a single
`_do_post_with_retry(self, client, *, json_body, noun, unit, index, total)` helper rather
than duplicating the loop. The two callers differ only in `json_body`/label fragments.

Key gotchas:
- `httpx.TimeoutException` MUST be caught before `httpx.RequestError` (subclass ordering).
- `sleep` is called only in the retry branch, never after the final failure.
- `_parse_retry_after` is cleanest as a `@staticmethod` using `math.isfinite` to guard
  `inf`/`nan`; import `math` locally (mirrors existing `import re` pattern in the same file).
- `attempt` starts at 0 so first-retry wait = `backoff_base * 2**0 = backoff_base`.
- Split the parametrized non-2xx test when some statuses are now retried (429/5xx) and
  others remain immediate (4xx≠429) — a single `@pytest.mark.parametrize` that expects
  immediate raise will fail for the retried ones.
