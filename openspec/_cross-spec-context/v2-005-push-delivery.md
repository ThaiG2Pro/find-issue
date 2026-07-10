## V2-005 — v2-005-push-delivery (S3 done: 2026-07-08)
### Dependencies (from other changes)
- delivery-6: `Delivery` port (`deliver(content: str) -> None`), `DeliveryError`, `FileDelivery`/`StdoutDelivery` adapter pattern, CLI catch block
- digest-renderer-5: `render(...) -> str` produces the `content` arg (INT-V2-005-001); `## {repo}` line is the split boundary
- github-collector-2: `httpx.Client(timeout=...)` usage pattern (ADR-001 reuse)
### Shared Decisions
- ADR-001: reuse httpx (no new dep) for outbound HTTP POST to webhook
- ADR-002: char-based two-level split (`len(str)` not bytes; repo boundary first, line fallback)
- ADR-003: webhook URL resolved from env + validated https + Discord host allowlist at config load
- ADR-004: no openapi.yaml — CLI tool, outbound client only (extends delivery-6/renderer-5/state-store-3 CLI-only ADR precedent)
### Exports (other changes may depend on these)
- `DiscordDelivery` — new `Delivery` adapter in `osspulse.delivery`; same `deliver(content: str) -> None` port
- `Config.webhook_url`, `Config.webhook_env` — new fields on the frozen dataclass (defaults: `None`, `"DISCORD_WEBHOOK_URL"`)
- `output_destination = "discord"` — third valid value for `[output] destination` in config
### Constraints Set (apply to subsequent changes)
- `Delivery` port signature is FROZEN — `deliver(self, content: str) -> None` — do NOT modify
- Any new delivery adapter must NOT import `osspulse.github/summarizer/cache/render` (AC-6-002, AC-V2-005-003)
- Webhook URL (and any future outbound-endpoint secret) must be env-var-only, never in config file, never logged, never in error messages
- Discord content limit is 2000 Unicode chars (not bytes); splitting a digest for any character-limited channel must use `len(str)`
---
