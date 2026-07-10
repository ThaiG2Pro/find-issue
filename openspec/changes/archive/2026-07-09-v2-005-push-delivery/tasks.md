# Tasks — v2-005-push-delivery

> Discord webhook push delivery. Order: config/model → adapter → wiring → tests.
> AC ids from `specs/delivery/spec.md`. No openapi.yaml (ADR-004, CLI tool).

## 1. Config model fields
- [x] 1.1 Add `webhook_url: str | None = None` and `webhook_env: str = "DISCORD_WEBHOOK_URL"` to the `Config` dataclass.
  - File: `src/osspulse/models.py`
  - _Requirements: AC-V2-005-012, BR-V2-005-005_

## 2. Config parsing + URL validation (fail-fast)
- [x] 2.1 Extend `[output]` parsing to accept `destination = "discord"` (alongside `file`/`stdout`); reject any other value with `ConfigError`.
  - File: `src/osspulse/config.py`
  - _Requirements: AC-6-012, AC-V2-005-012_
- [x] 2.2 When `destination == "discord"`: resolve the env var (name = `[output] webhook_env` or default `DISCORD_WEBHOOK_URL`); raise `ConfigError` if unset/empty. Store resolved URL + env name on `Config`.
  - File: `src/osspulse/config.py`
  - _Requirements: AC-V2-005-012, AC-V2-005-013, BR-V2-005-005_
- [x] 2.3 Validate the resolved URL: `urlparse` scheme must be `https`, host must be in the Discord allowlist (`discord.com`, `discordapp.com`); else `ConfigError` (SSRF/mis-route guard). Never log the URL.
  - File: `src/osspulse/config.py`
  - _Requirements: AC-V2-005-014, AC-V2-005-015, BR-V2-005-005_

## 3. Checkpoint — config layer
- [x] 3.1 **CHECKPOINT (human review + tests):** run config tests (`tests/test_config.py`) for the new `[output] discord` + env + https/host-allowlist cases. STOP and wait for user sign-off before building the adapter.
  - File: `tests/test_config.py`
  - _Requirements: AC-6-012, AC-V2-005-012, AC-V2-005-013, AC-V2-005-014, AC-V2-005-015_

## 4. Discord split helper (pure function)
- [x] 4.1 Implement `_split_for_discord(content: str, limit: int = 2000) -> list[str]`: greedy-accumulate `## ` repo sections up to `limit` chars; hard-split an oversized section by line; defensively char-slice a single line > `limit`. Measure with `len(str)` (Unicode chars, NOT bytes). A `content` ≤ limit returns `[content]`.
  - File: `src/osspulse/delivery/discord_delivery.py`
  - _Requirements: AC-V2-005-004, AC-V2-005-005, AC-V2-005-006, AC-V2-005-007, BR-V2-005-002, BR-V2-005-003_

## 5. DiscordDelivery adapter
- [x] 5.1 Implement `DiscordDelivery` with `__init__(self, webhook_url, timeout=10.0, client=None)` and `deliver(self, content)`: split via `_split_for_discord`, POST each message sequentially as `{"content": msg}` over the injected/constructed httpx client with the timeout. Implements the frozen `Delivery` port structurally (no subclassing, no port change).
  - File: `src/osspulse/delivery/discord_delivery.py`
  - _Requirements: AC-V2-005-001, AC-V2-005-002, BR-V2-005-001_
- [x] 5.2 Map failures to `DeliveryError`: non-2xx status (404/429/5xx), connection/DNS error, and timeout. The error message MUST be built from status/exception type — NEVER the webhook URL or an httpx request repr that embeds it. On a multi-message push, fail fatally at the first failed message (no rollback).
  - File: `src/osspulse/delivery/discord_delivery.py`
  - _Requirements: AC-V2-005-008, AC-V2-005-009, AC-V2-005-010, AC-V2-005-011, BR-V2-005-004_
- [x] 5.3 Keep the module free of upstream imports; inject the httpx client for testing instead.
  - File: `src/osspulse/delivery/discord_delivery.py`
  - _Requirements: AC-V2-005-003_
- [x] 5.4 Export `DiscordDelivery` from the delivery package.
  - File: `src/osspulse/delivery/__init__.py`
  - _Requirements: AC-V2-005-001_

## 6. Pipeline wiring
- [x] 6.1 Add `elif config.output_destination == "discord"` in the deliver-once block; preserve the existing file/stdout branches and the single `.deliver()` call (BR-7-007).
  - File: `src/osspulse/pipeline.py`
  - _Requirements: AC-V2-005-001, INT-V2-005-001_

## 7. Tests — split helper
- [x] 7.1 Unit-test `_split_for_discord`: content ≤2000 → one message; 2001 with multiple `## ` → ≥2 messages each ≤2000, in order; a single `## ` section >2000 → line-split, every message ≤2000; non-ASCII digest (chars ≤2000 but bytes >2000) → single message (char counting); empty/"No new items" → one short verbatim message.
  - File: `tests/delivery/test_discord_split.py`
  - _Requirements: AC-V2-005-004, AC-V2-005-005, AC-V2-005-006, AC-V2-005-007_

## 8. Tests — DiscordDelivery adapter
- [x] 8.1 Test happy path (mock httpx client, assert one POST per message with `{"content": ...}`, 2xx incl. 204 = success) and port-compat (structurally satisfies `Delivery`).
  - File: `tests/delivery/test_discord_delivery.py`
  - _Requirements: AC-V2-005-001, AC-V2-005-002_
- [x] 8.2 Test error mapping: 404/429/5xx, connection error, and timeout each → `DeliveryError`; assert the error message does NOT contain the webhook URL; multi-message where msg 2 fails → `DeliveryError` after msg 1 was POSTed.
  - File: `tests/delivery/test_discord_delivery.py`
  - _Requirements: AC-V2-005-008, AC-V2-005-009, AC-V2-005-010, AC-V2-005-011_
- [x] 8.3 Test import-decoupling: `osspulse.delivery.discord_delivery` does not import github/summarizer/cache/render (static inspection).
  - File: `tests/delivery/test_discord_delivery.py`
  - _Requirements: AC-V2-005-003_

## 9. Tests — config validation
- [x] 9.1 Test `[output] destination="discord"`: env set + valid https Discord URL → loads, `output_path` ignored; env unset/empty → `ConfigError`; http:// URL → `ConfigError`; non-Discord host → `ConfigError`; custom `webhook_env` name honored.
  - File: `tests/test_config.py`
  - _Requirements: AC-V2-005-012, AC-V2-005-013, AC-V2-005-014, AC-V2-005-015_

## 10. Final checkpoint
- [x] 10.1 **CHECKPOINT (final — human review):** run the module test suite (`tests/delivery/`, `tests/test_config.py`, `tests/test_pipeline.py`) with coverage per `sdlc.config.json` (diff 90 / lines 80 / branches 80); confirm no webhook URL appears in any test log/output; confirm all 15 ACs covered. STOP for sign-off before S5.
  - File: `tests/delivery/test_discord_delivery.py`
  - _Requirements: AC-V2-005-001, AC-V2-005-002, AC-V2-005-003, AC-V2-005-004, AC-V2-005-005, AC-V2-005-006, AC-V2-005-007, AC-V2-005-008, AC-V2-005-009, AC-V2-005-010, AC-V2-005-011, AC-V2-005-012, AC-V2-005-013, AC-V2-005-014, AC-V2-005-015_
