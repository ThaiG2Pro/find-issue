"""Tests for LiteLLMSummarizer — single-item and batch (AC-4-001..022).

Rules:
- All test names carry their AC-ID (R3).
- ``completion`` is injected as a callable mock — NO real LiteLLM/network (stack.md, A-C8).
- Use REAL ``litellm.exceptions.*`` instances in error tests (ADR-002 risk mitigation).
"""

import logging
from unittest.mock import MagicMock

import litellm.exceptions

from osspulse.models import RawItem, SummarizedItem
from osspulse.ports import LLMClient
from osspulse.summarizer.client import LiteLLMSummarizer
from osspulse.summarizer.config import SummarizerConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CFG = SummarizerConfig(model="openai/gpt-4o-mini")


def _item(**kwargs) -> RawItem:
    defaults = dict(
        repo="owner/repo", item_type="issue", item_id="1",
        title="Bug in parser", body="The parser crashes on empty input.",
        url="https://x", created_at="2024-01-01T00:00:00Z",
    )
    return RawItem(**{**defaults, **kwargs})


def _mock_response(text: str) -> MagicMock:
    """Build a minimal mock of litellm.completion()'s return value."""
    resp = MagicMock()
    resp.choices[0].message.content = text
    return resp


class _FakeCache:
    """In-memory SummaryCache that optionally raises on get or set."""

    def __init__(
        self,
        store: dict | None = None,
        raise_on_get: bool = False,
        raise_on_set: bool = False,
    ) -> None:
        self._store: dict[str, str] = store or {}
        self._raise_on_get = raise_on_get
        self._raise_on_set = raise_on_set
        self.set_calls: list[tuple[str, str]] = []

    def get(self, key: str) -> str | None:
        if self._raise_on_get:
            raise ConnectionError("Redis down")
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        if self._raise_on_set:
            raise ConnectionError("Redis down")
        self._store[key] = value
        self.set_calls.append((key, value))


def _summarizer(completion=None, cache=None) -> LiteLLMSummarizer:
    return LiteLLMSummarizer(
        provider="openai",
        api_key="test-key",
        cache=cache or _FakeCache(),
        config=_CFG,
        completion=completion or MagicMock(return_value=_mock_response("Good summary.")),
    )


# ---------------------------------------------------------------------------
# Protocol contract (AC-4-003)
# ---------------------------------------------------------------------------


def test_LLMClient_protocol_signature_unchanged_AC_4_003():
    """LLMClient Protocol still declares exactly summarize(item: RawItem) -> str (AC-4-003)."""
    import inspect
    sig = inspect.signature(LLMClient.summarize)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "item" in params
    # Return annotation is str
    assert sig.return_annotation is str


def test_LiteLLMSummarizer_satisfies_LLMClient_protocol_AC_4_003():
    """LiteLLMSummarizer structurally satisfies LLMClient (AC-4-003)."""
    s = _summarizer()
    assert callable(s.summarize)
    import inspect
    sig = inspect.signature(s.summarize)
    assert "item" in sig.parameters


# ---------------------------------------------------------------------------
# Cache hit (AC-4-004)
# ---------------------------------------------------------------------------


def test_cache_hit_returns_cached_no_llm_call_AC_4_004():
    """Cache hit returns cached value; completion is NOT called (AC-4-004)."""
    completion = MagicMock()
    item = _item()
    # Pre-populate cache with the key the summarizer would compute
    from osspulse.summarizer.keys import cache_key, content_hash
    from osspulse.summarizer.normalize import prepare_input
    t, b = prepare_input(item.title, item.body)
    key = cache_key(item, content_hash(t, b))
    cache = _FakeCache(store={key: "cached summary"})

    result = _summarizer(completion=completion, cache=cache).summarize(item)

    assert result == "cached summary"
    completion.assert_not_called()


# ---------------------------------------------------------------------------
# Cache miss → LLM called once → stored (AC-4-005)
# ---------------------------------------------------------------------------


def test_cache_miss_calls_llm_once_then_stores_AC_4_005():
    """Cache miss: completion called exactly once; result stored in cache (AC-4-005)."""
    cache = _FakeCache()
    completion = MagicMock(return_value=_mock_response("A clear summary."))
    s = _summarizer(completion=completion, cache=cache)

    result = s.summarize(_item())

    completion.assert_called_once()
    assert result == "A clear summary."
    assert len(cache.set_calls) == 1
    assert cache.set_calls[0][1] == "A clear summary."


# ---------------------------------------------------------------------------
# Cache key format end-to-end (AC-4-006)
# ---------------------------------------------------------------------------


def test_cache_key_format_end_to_end_AC_4_006():
    """The key stored in cache matches summary:{repo}:{type}:{id}:{hash} (AC-4-006)."""
    from osspulse.summarizer.keys import cache_key, content_hash
    from osspulse.summarizer.normalize import prepare_input
    cache = _FakeCache()
    item = _item(repo="a/b", item_type="issue", item_id="99")
    _summarizer(cache=cache).summarize(item)
    t, b = prepare_input(item.title, item.body)
    expected_key = cache_key(item, content_hash(t, b))
    assert cache.set_calls[0][0] == expected_key
    assert expected_key.startswith("summary:a/b:issue:99:")


# ---------------------------------------------------------------------------
# Cache-get failure → treated as miss (AC-4-013)
# ---------------------------------------------------------------------------


def test_cache_get_failure_treated_as_miss_AC_4_013():
    """Redis get raises → treated as miss; LLM called; no exception raised (AC-4-013)."""
    completion = MagicMock(return_value=_mock_response("Summary despite Redis down."))
    cache = _FakeCache(raise_on_get=True)

    result = _summarizer(completion=completion, cache=cache).summarize(_item())

    assert result == "Summary despite Redis down."
    completion.assert_called_once()


# ---------------------------------------------------------------------------
# Cache-set failure → summary still returned (AC-4-014)
# ---------------------------------------------------------------------------


def test_cache_set_failure_summary_still_returned_AC_4_014():
    """Redis set raises → summary still returned; no exception raised (AC-4-014)."""
    completion = MagicMock(return_value=_mock_response("Good summary."))
    cache = _FakeCache(raise_on_set=True)

    result = _summarizer(completion=completion, cache=cache).summarize(_item())

    assert result == "Good summary."


# ---------------------------------------------------------------------------
# Empty body → title-only call (AC-4-017)
# ---------------------------------------------------------------------------


def test_empty_body_calls_llm_with_title_only_AC_4_017():
    """Empty body item: LLM is called (with title) and returns a summary (AC-4-017)."""
    completion = MagicMock(return_value=_mock_response("Title-based summary."))
    result = _summarizer(completion=completion).summarize(_item(body=""))
    completion.assert_called_once()
    assert result == "Title-based summary."


# ---------------------------------------------------------------------------
# Huge body → truncated before hashing (AC-4-019)
# ---------------------------------------------------------------------------


def test_huge_body_truncated_and_hashed_post_truncation_AC_4_019():
    """Body > 8000 chars is truncated; cache key uses the truncated hash (AC-4-019)."""
    from osspulse.summarizer.keys import cache_key, content_hash
    cap = _CFG.input_char_cap  # 8000
    huge_body = "x" * 20_000
    item = _item(body=huge_body)
    cache = _FakeCache()
    _summarizer(cache=cache).summarize(item)

    t_trunc = item.title.strip()[:cap]
    b_trunc = huge_body.strip()[:cap]
    expected_key = cache_key(item, content_hash(t_trunc, b_trunc))
    assert cache.set_calls[0][0] == expected_key


# ---------------------------------------------------------------------------
# API key sourced from config, never a literal (AC-4-022)
# ---------------------------------------------------------------------------


def test_api_key_passed_to_completion_not_hardcoded_AC_4_022():
    """api_key is passed to completion(); no secret literal in module source (AC-4-022)."""
    completion = MagicMock(return_value=_mock_response("ok."))
    LiteLLMSummarizer(
        provider="openai", api_key="secret-key-123",
        cache=_FakeCache(), config=_CFG, completion=completion,
    ).summarize(_item())
    _, kwargs = completion.call_args
    assert kwargs.get("api_key") == "secret-key-123"

    # Source file must not contain any hardcoded key-looking string
    import inspect

    import osspulse.summarizer.client as mod
    src = inspect.getsource(mod)
    assert "secret-key" not in src
    assert "sk-" not in src


def test_timeout_passed_to_completion_RF2():
    """request_timeout_seconds is forwarded to completion(timeout=...) (RF-2, ADR-007)."""
    completion = MagicMock(return_value=_mock_response("ok."))
    cfg = SummarizerConfig(model="openai/gpt-4o-mini", request_timeout_seconds=42.0)
    LiteLLMSummarizer(
        provider="openai", api_key=None,
        cache=_FakeCache(), config=cfg, completion=completion,
    ).summarize(_item())
    _, kwargs = completion.call_args
    assert kwargs.get("timeout") == 42.0


# ---------------------------------------------------------------------------
# summarize_items — batch degradation (AC-4-009..012, AC-4-018, AC-4-020, AC-4-021)
# ---------------------------------------------------------------------------


def test_llm_timeout_item_skipped_others_summarized_AC_4_009():
    """Timeout on item B: A and C produce SummarizedItems; B absent; no raise (AC-4-009)."""
    item_a = _item(item_id="1", title="A", body="Body A.")
    item_b = _item(item_id="2", title="B", body="Body B.")
    item_c = _item(item_id="3", title="C", body="Body C.")

    def fake_completion(**kwargs):
        msg = kwargs["messages"][1]["content"]
        if "Body B." in msg:
            raise litellm.exceptions.Timeout(  # REAL exception (ADR-002)
                message="timeout", model="m", llm_provider="openai"
            )
        return _mock_response("Good summary.")

    s = _summarizer(completion=fake_completion)
    result = s.summarize_items([item_a, item_b, item_c])

    ids = [r.raw.item_id for r in result]
    assert "1" in ids
    assert "3" in ids
    assert "2" not in ids


def test_llm_4xx_item_skipped_AC_4_010(caplog):
    """BadRequestError (4xx): item skipped, run continues (AC-4-010)."""
    item = _item(item_id="10", title="T", body="B.")

    def fake_completion(**kwargs):
        raise litellm.exceptions.BadRequestError(  # REAL exception (ADR-002)
            message="bad request", model="m", llm_provider="openai"
        )

    with caplog.at_level(logging.WARNING):
        result = _summarizer(completion=fake_completion).summarize_items([item])
    assert result == []


def test_llm_5xx_item_skipped_AC_4_010():
    """InternalServerError (5xx): item skipped (AC-4-010)."""
    def fake_completion(**kwargs):
        raise litellm.exceptions.InternalServerError(
            message="server error", model="m", llm_provider="openai"
        )
    result = _summarizer(completion=fake_completion).summarize_items([_item()])
    assert result == []


def test_llm_rate_limit_item_skipped_AC_4_010():
    """RateLimitError (429): item skipped (AC-4-010)."""
    def fake_completion(**kwargs):
        raise litellm.exceptions.RateLimitError(
            message="rate limit", model="m", llm_provider="openai"
        )
    result = _summarizer(completion=fake_completion).summarize_items([_item()])
    assert result == []


def test_item_b_fails_a_c_succeed_AC_4_011():
    """A and C succeed; B (LLM error) is absent from results (AC-4-011)."""
    item_a = _item(item_id="a", title="A", body="Body A.")
    item_b = _item(item_id="b", title="B", body="Body B.")
    item_c = _item(item_id="c", title="C", body="Body C.")

    def fake_completion(**kwargs):
        if "Body B." in kwargs["messages"][1]["content"]:
            raise litellm.exceptions.APIError(
                message="error", status_code=500, llm_provider="openai", model="m"
            )
        return _mock_response("A summary.")

    result = _summarizer(completion=fake_completion).summarize_items(
        [item_a, item_b, item_c]
    )
    assert [r.raw.item_id for r in result] == ["a", "c"]
    assert all(isinstance(r, SummarizedItem) for r in result)


def test_failure_log_no_api_key_or_prompt_AC_4_012(caplog):
    """Failure log contains identity but NOT api_key or prompt body (AC-4-012)."""
    item = _item(item_id="7", title="T", body="Secret body content.")

    def fake_completion(**kwargs):
        raise litellm.exceptions.RateLimitError(
            message="rate limit", model="m", llm_provider="openai"
        )

    with caplog.at_level(logging.WARNING):
        _summarizer(completion=fake_completion).summarize_items([item])

    log_text = " ".join(caplog.messages)
    assert "owner/repo/issue/7" in log_text  # identity present
    assert "test-key" not in log_text          # key absent
    assert "Secret body content" not in log_text  # body absent


def test_fully_empty_item_skipped_no_llm_call_AC_4_018():
    """Item with empty title+body is skipped; completion never called (AC-4-018)."""
    completion = MagicMock()
    result = _summarizer(completion=completion).summarize_items(
        [_item(title="", body="")]
    )
    assert result == []
    completion.assert_not_called()


def test_second_run_unchanged_items_zero_llm_calls_AC_4_020():
    """Second run over identical items: every item is a cache hit; 0 LLM calls (AC-4-020)."""
    completion = MagicMock(return_value=_mock_response("First run summary."))
    cache = _FakeCache()
    s = _summarizer(completion=completion, cache=cache)
    items = [_item(item_id=str(i), body=f"Body {i}.") for i in range(3)]

    s.summarize_items(items)          # run 1 — fills cache
    completion.reset_mock()
    s.summarize_items(items)          # run 2 — all cache hits

    completion.assert_not_called()


def test_no_github_or_state_import_AC_4_021():
    """summarizer/ and cache/ modules do not import osspulse.github or osspulse.state (AC-4-021)."""
    import importlib
    import pkgutil

    import osspulse.cache
    import osspulse.summarizer

    forbidden = {"osspulse.github", "osspulse.state"}
    for pkg in (osspulse.summarizer, osspulse.cache):
        for _, mod_name, _ in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
            mod = importlib.import_module(mod_name)
            for dep in vars(mod).values():
                if hasattr(dep, "__module__") and dep.__module__:
                    for f in forbidden:
                        assert not dep.__module__.startswith(f), (
                            f"{mod_name} imports {f}"
                        )


def test_empty_llm_output_item_skipped_EC_012():
    """LLM returns empty string → SummarizationFailed → item skipped (EC-012)."""
    completion = MagicMock(return_value=_mock_response(""))
    result = _summarizer(completion=completion).summarize_items([_item()])
    assert result == []
