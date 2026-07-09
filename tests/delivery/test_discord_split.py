"""Unit tests for _split_for_discord (AC-V2-005-004..007)."""

from osspulse.delivery.discord_delivery import _split_for_discord

LIMIT = 2000


# ---------------------------------------------------------------------------
# AC-V2-005-004 — content ≤ 2000 chars → exactly one message
# ---------------------------------------------------------------------------


def test_short_content_returns_single_message():
    """Content ≤ 2000 chars → single message unchanged (AC-V2-005-004)."""
    content = "# OSS Pulse Digest\n\nNo new items in the last 7 days\n"
    result = _split_for_discord(content, limit=LIMIT)
    assert result == [content]


def test_exactly_2000_chars_returns_single_message():
    """Content of exactly 2000 chars → single message (AC-V2-005-004 boundary)."""
    content = "x" * LIMIT
    result = _split_for_discord(content, limit=LIMIT)
    assert len(result) == 1
    assert len(result[0]) == LIMIT


def test_empty_content_returns_single_message():
    """Empty / 'No new items' short digest → one message verbatim (AC-V2-005-004)."""
    content = "# OSS Pulse Digest\n\nNo new items in the last 7 days\n"
    result = _split_for_discord(content, limit=LIMIT)
    assert len(result) == 1
    assert result[0] == content


# ---------------------------------------------------------------------------
# AC-V2-005-005 — digest split into multiple messages, all content preserved, in order
# ---------------------------------------------------------------------------


def test_multi_section_split_preserves_all_content():
    """Multi-section digest split → messages joined == original content (AC-V2-005-005)."""
    # Build a digest with 3 repo sections, total > 2000
    section = "## owner/repo — 7 ngày qua\n" + ("- #1 line\n" * 80)  # ~1120 chars each
    content = "# OSS Pulse Digest\n\n" + section + section + section
    assert len(content) > LIMIT

    result = _split_for_discord(content, limit=LIMIT)

    assert len(result) >= 2
    assert "".join(result) == content


def test_multi_section_split_each_message_within_limit():
    """Every message in a multi-section split is ≤ 2000 chars (AC-V2-005-005)."""
    section = "## owner/repo — 7 ngày qua\n" + ("- #1 line\n" * 80)
    content = "# OSS Pulse Digest\n\n" + section + section + section

    result = _split_for_discord(content, limit=LIMIT)

    for i, msg in enumerate(result):
        assert len(msg) <= LIMIT, f"message {i} exceeds limit: {len(msg)}"


def test_section_order_preserved():
    """Repo sections appear in the same order in output as in input (AC-V2-005-005)."""
    s1 = "## alpha/repo — 7 ngày qua\n" + ("- #1 item line of text here\n" * 120)
    s2 = "## beta/repo — 7 ngày qua\n" + ("- #2 item line of text here\n" * 120)
    content = "# OSS Pulse Digest\n\n" + s1 + s2
    assert len(content) > LIMIT, f"test setup: content len={len(content)} must exceed {LIMIT}"

    result = _split_for_discord(content, limit=LIMIT)
    joined = "".join(result)

    assert joined.index("alpha/repo") < joined.index("beta/repo")


# ---------------------------------------------------------------------------
# AC-V2-005-006 — single oversized section → line-split, still ≤ 2000 per message
# ---------------------------------------------------------------------------


def test_single_oversized_section_is_line_split():
    """A single ## section > 2000 chars is line-split; each message ≤ 2000 (AC-V2-005-006)."""
    big_section = "## giant/repo — 7 ngày qua\n" + ("- #1 very long item line\n" * 120)
    assert len(big_section) > LIMIT

    result = _split_for_discord(big_section, limit=LIMIT)

    assert len(result) >= 2
    for i, msg in enumerate(result):
        assert len(msg) <= LIMIT, f"message {i} length {len(msg)} exceeds limit"


def test_pathological_single_line_is_char_sliced():
    """A single line > 2000 chars is char-sliced; no message exceeds limit (AC-V2-005-006)."""
    # One enormously long line with no newlines
    single_line = "## repo — 7 ngày qua\n" + "x" * 3000
    result = _split_for_discord(single_line, limit=LIMIT)

    for i, msg in enumerate(result):
        assert len(msg) <= LIMIT, f"message {i} length {len(msg)} exceeds limit"


# ---------------------------------------------------------------------------
# AC-V2-005-007 — char counting (not bytes) for non-ASCII content
# ---------------------------------------------------------------------------


def test_non_ascii_counted_as_chars_not_bytes():
    """Non-ASCII content ≤ 2000 chars but > 2000 bytes → single message (AC-V2-005-007)."""
    # 'Ế' is 3 bytes in UTF-8; 700 × 3 = 2100 bytes but only 700 chars
    non_ascii = "# OSS Pulse Digest\n\nKhác: " + "Ế" * 700 + "\n"
    assert len(non_ascii) < LIMIT, f"test setup: char count {len(non_ascii)} must be < {LIMIT}"
    assert len(non_ascii.encode("utf-8")) > LIMIT, (
        f"test setup: byte count {len(non_ascii.encode())} must exceed {LIMIT}"
    )

    result = _split_for_discord(non_ascii, limit=LIMIT)

    assert len(result) == 1, "non-ASCII content within char limit must not be split"
    assert result[0] == non_ascii


def test_emoji_counted_as_single_char():
    """An emoji counts as 1 character, not 4 bytes (AC-V2-005-007)."""
    # 🔥 is 4 bytes; 1000 emoji = 4000 bytes but only 1000 chars → single message
    content = "# OSS Pulse\n" + "🔥" * 990
    assert len(content) < LIMIT
    assert len(content.encode("utf-8")) > LIMIT

    result = _split_for_discord(content, limit=LIMIT)
    assert len(result) == 1


def test_mixed_ascii_and_non_ascii_split_correctly():
    """Mixed ASCII + non-ASCII digest splits without exceeding char limit (AC-V2-005-007)."""
    # Two sections each with Vietnamese text; combined > 2000 chars
    section = "## owner/repo — 7 ngày qua\n" + ("- Vấn đề mới: tiêu đề\n" * 60)
    content = "# OSS Pulse Digest\n\n" + section + section
    assert len(content) > LIMIT

    result = _split_for_discord(content, limit=LIMIT)

    for i, msg in enumerate(result):
        assert len(msg) <= LIMIT, f"message {i} len={len(msg)} exceeds limit"
    assert "".join(result) == content


# ---------------------------------------------------------------------------
# Custom limit for deterministic boundary tests
# ---------------------------------------------------------------------------


def test_custom_limit_boundary():
    """Split respects a custom limit parameter (boundary at exactly limit chars)."""
    limit = 50
    section_a = "## a/repo — 7 days\n" + "x" * 20  # 39 chars
    section_b = "## b/repo — 7 days\n" + "y" * 20  # 39 chars
    content = section_a + "\n" + section_b  # 79 chars > 50

    result = _split_for_discord(content, limit=limit)

    assert len(result) >= 2
    for msg in result:
        assert len(msg) <= limit
