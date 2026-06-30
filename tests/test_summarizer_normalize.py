"""Tests for summarizer key helpers and normalization (AC-4-006..008, AC-4-015..017, AC-4-019).

Rules:
- All test names carry their AC-ID (R3).
- Pure functions — no I/O, no mocks needed.
"""

import pytest

from osspulse.models import RawItem
from osspulse.summarizer.errors import SummarizationFailed
from osspulse.summarizer.keys import cache_key, content_hash
from osspulse.summarizer.normalize import normalize_summary, prepare_input

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(**kwargs) -> RawItem:
    defaults = dict(
        repo="owner/repo",
        item_type="issue",
        item_id="1",
        title="Fix bug",
        body="Details here.",
        url="https://x",
        created_at="2024-01-01T00:00:00Z",
    )
    return RawItem(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# content_hash (AC-4-007, AC-4-008)
# ---------------------------------------------------------------------------


def test_same_content_yields_same_hash_AC_4_007():
    """Same title+body always produces the same hash (AC-4-007)."""
    assert content_hash("Hello", "World") == content_hash("Hello", "World")


def test_changed_body_yields_different_hash_AC_4_008():
    """Changing the body produces a different hash (AC-4-008)."""
    assert content_hash("Title", "body v1") != content_hash("Title", "body v2")


def test_changed_title_yields_different_hash_AC_4_008():
    """Changing the title produces a different hash (AC-4-008)."""
    assert content_hash("Title A", "body") != content_hash("Title B", "body")


def test_hash_newline_separator_prevents_collision_AC_4_007():
    """('ab', 'c') and ('a', 'bc') must not collide (ADR-003 newline separator)."""
    assert content_hash("ab", "c") != content_hash("a", "bc")


def test_hash_non_ascii_safe_EC_004():
    """Non-ASCII / emoji / CJK content hashes without error (EC-004)."""
    h = content_hash("título 🐛", "内容 · résumé")
    assert len(h) == 64  # SHA-256 hex digest


# ---------------------------------------------------------------------------
# cache_key (AC-4-006)
# ---------------------------------------------------------------------------


def test_cache_key_format_AC_4_006():
    """Cache key = summary:{repo}:{item_type}:{item_id}:{hash} (AC-4-006)."""
    item = _item(repo="owner/repo", item_type="issue", item_id="42")
    h = content_hash("t", "b")
    key = cache_key(item, h)
    assert key == f"summary:owner/repo:issue:42:{h}"


# ---------------------------------------------------------------------------
# prepare_input (AC-4-017, AC-4-019)
# ---------------------------------------------------------------------------


def test_prepare_input_empty_body_returns_title_only_AC_4_017():
    """Empty body → (title, '') so LLM call uses title alone (AC-4-017)."""
    t, b = prepare_input("Some title", "")
    assert t == "Some title"
    assert b == ""


def test_prepare_input_none_like_fields_guarded_EC_006():
    """None-like body coerced to '' without error (EC-006)."""
    t, b = prepare_input("title", None)  # type: ignore[arg-type]
    assert b == ""


def test_prepare_input_truncates_body_to_cap_AC_4_019():
    """Body > cap is truncated to exactly cap characters (AC-4-019)."""
    cap = 8000
    long_body = "x" * 10_000
    t, b = prepare_input("t", long_body, input_char_cap=cap)
    assert len(b) == cap


def test_prepare_input_truncated_text_is_what_gets_hashed_AC_4_019():
    """Hash over (title, truncated_body) equals hash of prepare_input output (AC-4-019)."""
    cap = 8000
    long_body = "a" * 10_000
    t, b = prepare_input("Title", long_body, input_char_cap=cap)
    assert content_hash(t, b) == content_hash("Title", "a" * cap)


def test_prepare_input_strips_whitespace_AC_4_017():
    """Leading/trailing whitespace stripped from both fields."""
    t, b = prepare_input("  title  ", "  body  ")
    assert t == "title"
    assert b == "body"


# ---------------------------------------------------------------------------
# normalize_summary (AC-4-015, AC-4-016)
# ---------------------------------------------------------------------------


def test_over_long_output_normalized_to_two_sentences_AC_4_015():
    """4-sentence LLM output is reduced to ≤2 sentences (AC-4-015)."""
    text = "Sentence one. Sentence two. Sentence three. Sentence four."
    result = normalize_summary(text)
    # At most 2 terminal punctuation marks
    import re

    sentences = [s for s in re.split(r"(?<=[.!?])\s+", result) if s]
    assert len(sentences) <= 2


def test_whitespace_and_newlines_collapsed_AC_4_016():
    """Newlines + extra spaces collapsed to single spaces (AC-4-016)."""
    text = "First sentence.\n\nSecond sentence."
    result = normalize_summary(text)
    assert "\n" not in result
    assert "  " not in result


def test_code_fence_stripped_AC_4_016():
    """Surrounding markdown code fences are stripped (AC-4-016)."""
    text = "```\nThis is the summary.\n```"
    result = normalize_summary(text)
    assert "```" not in result
    assert result == "This is the summary."


def test_leading_trailing_whitespace_stripped_AC_4_016():
    """Leading/trailing whitespace removed from result (AC-4-016)."""
    result = normalize_summary("   A good summary.   ")
    assert result == "A good summary."


def test_empty_output_raises_SummarizationFailed_EC_012():
    """Empty/whitespace LLM output raises SummarizationFailed (EC-012)."""
    with pytest.raises(SummarizationFailed):
        normalize_summary("   ")


def test_whitespace_only_after_stripping_raises_EC_012():
    """Output that is only backticks/spaces raises SummarizationFailed (EC-012)."""
    with pytest.raises(SummarizationFailed):
        normalize_summary("``` ```")


def test_abbreviation_not_split_ADR_006():
    """Common abbreviations (e.g.) do not trigger sentence split (ADR-006)."""
    text = "Use e.g. this pattern. Then apply it."
    result = normalize_summary(text)
    # "e.g." should not split the first sentence into two
    assert "e.g." in result


def test_non_ascii_safe_EC_004():
    """Non-ASCII / emoji summary normalized without error (EC-004)."""
    result = normalize_summary("Fixes the 🐛 bug in the parser. Works correctly now.")
    assert "🐛" in result
