## 1. Constructor — inject retry params

- [x] 1.1 Add `import time` and `from collections.abc import Callable` (or `typing.Callable`); extend `DiscordDelivery.__init__` with `max_retries: int = 3`, `backoff_base: float = 1.0`, `sleep: Callable[[float], None] = time.sleep`, storing each on `self` (`self._max_retries`, `self._backoff_base`, `self._sleep`). Defaults keep existing call sites unchanged. File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-001-011_

## 2. Shared retry helper

- [x] 2.1 Add `_parse_retry_after(response) -> float | None`: read the `Retry-After` header, return a finite float when numeric, else `None` (missing/empty/non-numeric never raises). File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-001-006_
- [x] 2.2 Add `_do_post_with_retry(self, client, *, json_body, noun, unit, index, total)`: run the attempt loop from design §Sequence Flows — POST `json_body`; on `2xx` return; classify transient (`429`/`5xx`/`TimeoutException`/`RequestError`) vs non-transient (`4xx`≠`429`); when transient and `attempt < self._max_retries`, wait `max(retry_after, backoff_base*2**attempt)` (or pure `backoff_base*2**attempt` when no numeric `Retry-After`), call `self._sleep(wait)`, increment, continue; otherwise raise `DeliveryError` composed from HTTP status code or exception **type name** only (never `str(exc)`/`repr(request)`, never the URL). `sleep` is called only between attempts, never after the final failed one. File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-001-001, AC-001-002, AC-001-003, AC-001-004, AC-001-005, AC-001-006, AC-001-007, AC-001-010, AC-001-011, AC-V2-005-008, AC-V2-005-009, AC-V2-005-010, AC-V2-005-011_

## 3. Refactor the two POST paths onto the helper

- [x] 3.1 Refactor `_post_one` to delegate to `_do_post_with_retry(client, json_body={"content": msg}, noun="discord delivery", unit="message", index=index, total=total)`, removing its inline try/except/status-check. File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-001-001, AC-001-002, AC-001-004, AC-V2-005-008, AC-V2-005-011_
- [x] 3.2 Refactor `_post_one_embed` to delegate to `_do_post_with_retry(client, json_body={"embeds": embeds}, noun="discord embed delivery", unit="batch", index=index, total=total)` so embed POSTs use the identical retry policy (no drift). File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-001-008, AC-V4-001-007_

## 4. Checkpoint — mid-build review

- [x] 4.1 CHECKPOINT: `deliver()`/`_post_all`/`_post_embed_batches` and all parse/split/embed helpers unchanged; both POST paths route through the single retry helper; final error still built from status/type-name only. Run existing suite to confirm no regression in unchanged behavior, then STOP for human review before touching tests. File: `src/osspulse/delivery/discord_delivery.py` _Requirements: AC-001-008, AC-V2-005-011_

## 5. Update & add tests

- [x] 5.1 Split the parametrized `test_non_2xx_raises_delivery_error` (`[400,401,404,429,500,503]`): keep `[400,401,404]` as immediate-error (assert exactly one POST, `sleep` never called); move `[429,500,503]` to new retry-then-error tests with injected `sleep` + bounded `max_retries`. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-004, AC-001-002_
- [x] 5.2 Add transient-success-on-retry tests: `503`-then-`204` and `RequestError`-then-`204` with `max_retries=3` → returns normally, 2 POSTs, `sleep` called once. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-001, AC-001-005_
- [x] 5.3 Add retries-exhausted tests: all `500` (`max_retries=3` → 4 POSTs, 3 sleeps, `DeliveryError`) and all `TimeoutException` (`max_retries=2` → 3 POSTs, 2 sleeps, error mentions timeout). File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-002, AC-001-003_
- [x] 5.4 Add non-transient-immediate test: `403` → one POST, `sleep` never called, `DeliveryError`. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-004_
- [x] 5.5 Add `Retry-After` tests: `429` + `Retry-After: 5` (`backoff_base=1.0`) → `sleep` called with `5` (`max(5,1.0)`); `429` + missing and non-numeric (`soon`) `Retry-After` → no crash, `sleep` called with the pure backoff value. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-006, AC-001-005_
- [x] 5.6 Add backoff-growth test: 3 consecutive transient failures (`backoff_base=1.0`) → successive `sleep` args follow `backoff_base*2**attempt` (e.g. `[1,2,4]`), non-decreasing. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-007_
- [x] 5.7 Add embed-parity test: embed batch POST `429`-then-`204` (`use_embeds=True`) → retried, returns normally, `sleep` called once. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-008_
- [x] 5.8 Add per-message-budget test: content splits into 2 messages, msg 1 `204`, msg 2 `503`-then-`204` → msg 1 delivered once (not re-sent), msg 2 retried on its own budget then delivered. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-009_
- [x] 5.9 Add `max_retries=0` test: transient `503` → exactly one POST, `sleep` never called, `DeliveryError` immediately. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-011_
- [x] 5.10 Add post-retry URL-secrecy test: all attempts fail transiently (`500` / `TimeoutException`) → final `DeliveryError` contains neither the webhook URL nor `secret_token`. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-010, AC-V2-005-011_

## 6. Checkpoint — final

- [x] 6.1 CHECKPOINT (FINAL): run the module test suite (`pytest tests/delivery/ -q`) + `ruff check`/`ruff format --check` on the touched files; confirm coverage ≥80% and every new/modified AC (AC-001-001..011, AC-V2-005-008..011, AC-V4-001-007) has a passing test. STOP for human sign-off. File: `tests/delivery/test_discord_delivery.py` _Requirements: AC-001-001, AC-001-002, AC-001-003, AC-001-004, AC-001-005, AC-001-006, AC-001-007, AC-001-008, AC-001-009, AC-001-010, AC-001-011, AC-V2-005-008, AC-V2-005-009, AC-V2-005-010, AC-V2-005-011, AC-V4-001-007_
