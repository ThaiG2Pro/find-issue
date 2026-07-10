## 2026-07-06 — v2-003-releases: AuthError is a CollectorError subclass — never list base in inner guards

When designing a narrow inner `try/except` that must let `AuthError` propagate as fatal, do NOT
include `CollectorError` as a catch type — `AuthError` is a subclass of `CollectorError`, so it
would be silently swallowed by the inner guard and never reach the outer fatal arm.

**Pattern for inner guards in _collect_all:**
```python
except (InvalidRepoError, NetworkError) as exc:
    ...  # recoverable
except CollectorError as exc:
    if isinstance(exc, (AuthError, RateLimitError)):
        raise  # fatal / terminal — must NOT be swallowed
    logger.warning(...)
    releases = []
```

**Root cause of catch-all trap:** `AuthError(CollectorError)` and `RateLimitError(CollectorError)`.
Listing the base class in any except tuple catches all subclasses including fatal ones.

## 2026-07-06 — v2-003-releases: MagicMock collector compatibility — stub ALL new public methods

When `_collect_all` gains a new `collector.fetch_X(...)` call, EVERY existing test that uses
`mock_collector = MagicMock()` and calls into `_collect_all` (directly or via `run_pipeline`)
will silently get a `MagicMock` return from the unstubbed method. If the code does
`list_a + mock_return`, the result is `TypeError` at runtime (not at mock-setup time).

**Fix pattern:**
```python
mock_collector = MagicMock()
mock_collector.fetch_releases.return_value = []  # stub any new method with safe empty list
mock_collector.fetch_items.return_value = [...]   # then the method under test
```

Grep the test file for every `mock_collector = MagicMock()` after adding the new call and add
the stub. A Python script is faster than manual `str_replace` for >10 occurrences.

## 2026-07-06 — v2-003-releases: str_replace with method def as separator deletes the method

When inserting a new method ABOVE an existing method via `str_replace`, if `old_str` ends with
`    def fetch_items(self, ...):` as a "split point" and `new_str` does NOT include that line, the
method definition disappears from the class (its body becomes orphaned code inside the new method).

**Prevention:** always end `new_str` with the `def` line of the method that follows, and immediately
verify with `grep -n "def fetch_" client.py` after the write. The symptom is `AttributeError:
'GitHubCollector' object has no attribute 'fetch_items'` on test run.
