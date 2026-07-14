## 001 — discord-retry (S3 done: 2026-07-14)
### Dependencies (from other changes)
- v2-005-push-delivery: DiscordDelivery adapter, DeliveryError, webhook URL secrecy contract (T1)
- v4-discord-embeds: _post_one_embed, embed batch POST path now also retried
### Shared Decisions
- ADR-001: single `_do_post_with_retry` helper shared by plain-text + embed POST paths — prevents drift
- ADR-002: backoff = `max(Retry-After, backoff_base*2**attempt)`; attempt starts at 0; sleep only between attempts
### Exports (other changes may depend on these)
- `DiscordDelivery` — now accepts `max_retries`, `backoff_base`, `sleep` constructor params (all defaulted; backward compatible)
### Constraints Set (apply to subsequent changes)
- DeliveryError messages must never contain the webhook URL (use status code / exception type name only — T1/AC-V2-005-011 still enforced)
- Transient = {429, 5xx, TimeoutException, RequestError}; non-transient = 4xx except 429 — do not expand/change classification without a spec change
- `sleep` param on DiscordDelivery is for test injection only; production always uses default `time.sleep`
---
