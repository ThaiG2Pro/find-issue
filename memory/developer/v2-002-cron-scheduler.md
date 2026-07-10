## 2026-07-03 — v2-002-cron-scheduler: CliRunner mix_stderr kwarg not supported in Typer 0.26+

Typer 0.26.x `CliRunner.__init__` only accepts `charset` and `env`. The `mix_stderr=False` kwarg
raises `TypeError` at test collection time. Use plain `CliRunner()` — `result.stderr` and
`result.stdout` are available as separate attributes regardless.

**Fix**: remove `mix_stderr=False` from `CliRunner(...)` instantiation.

## 2026-07-03 — v2-002-cron-scheduler: Ruff UP042 — class Preset(str, Enum) vs StrEnum

Ruff rule UP042 rejects `class X(str, Enum)` and requires `class X(StrEnum)` on Python 3.11+.
`StrEnum` is in `enum` stdlib (Python 3.11+); `from enum import StrEnum`. Semantically identical.
Always use `StrEnum` for string enums in new code.

## 2026-07-03 — v2-002-cron-scheduler: fcntl.flock test — real fds required

The architect ADR specifies real file-descriptor testing for `fcntl.flock` semantics (not mocked).
Pattern: `fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)` + `fcntl.flock(fd, LOCK_EX|LOCK_NB)`.
Always clean up with `LOCK_UN` + `os.close(fd)` in a `finally` block, or the lock leaks into
subsequent tests in the same process (they share the fd table).

## 2026-07-03 — v2-002-cron-scheduler: Typer is_flag DeprecationWarning is cosmetic

`is_flag=True` on Typer options produces a DeprecationWarning in Typer 0.26+ but does NOT break
anything. Tests produce 3 warnings. This is safe to ignore; removing `is_flag` would change the
CLI API. Log the warning in the test output and move on.

## 2026-07-03 — v2-002-cron-scheduler: crontab round-trip newline sentinel

The `upsert_block` / `remove_block` newline contract:
- `upsert_block` ALWAYS prepends `\n` separator when `current` is non-empty (even if it already ends with `\n`) — the double-`\n` is the unconditional sentinel.
- `remove_block` unconditionally strips `current[start_idx-1]` (the separator) when `start_idx > 0`.
- This means: upsert on `"content\n"` produces `"content\n\n# >>> osspulse >>>...\n"`, and remove restores exactly `"content\n"`.

Do NOT try to be "smart" and skip the separator when the content already ends with `\n` — that breaks the remove symmetry and the round-trip guarantee.
