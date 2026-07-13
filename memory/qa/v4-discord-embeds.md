## 2026-07-13 — v4-discord-embeds: config bool-trap tests always separate from delivery-layer defaults

**Lesson**: When a feature adds a config-layer validation (`_validate_X` in `config.py`) AND a
delivery-layer default (`__init__(use_x: bool = False)`), tests for both layers must be written
independently. It is easy to write a test labeled `AC-X-008` that only exercises the delivery
default without ever calling `load_config` — leaving the `ConfigError` branch uncovered.

Pattern to apply to future changes with `[section] bool_flag = false/true` config keys:
- Always add at least 3 tests to `test_config.py`:
  1. Non-bool string (`"yes"`) → `ConfigError`
  2. Non-bool int (`1`) → `ConfigError`
  3. Absent section → default value on `Config`
- The delivery-layer `__init__` default test is NOT a substitute for the above.

**Context**: `discord_delivery.py:73` was correct; only the test coverage was missing.
Coverage report (`--cov-report=term-missing`) is the reliable way to catch this — line numbers
of missed branches are explicit.
