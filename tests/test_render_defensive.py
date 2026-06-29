"""Defensive-field and bucketing tests for the Digest Renderer (AC-5-015..020, EC-002..005/009/011).

Rules:
- All test names carry their AC-ID (R3).
- Pure function — no mocks needed.
"""

from osspulse.models import RawItem, SummarizedItem
from osspulse.render import render

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw(
    repo: str = "r/x",
    item_type: str = "issue",
    item_id: str = "1",
    title: str = "Title",
    url: str = "https://gh/1",
) -> RawItem:
    return RawItem(
        repo=repo,
        item_type=item_type,
        item_id=item_id,
        title=title,
        body="",
        url=url,
        created_at="2024-01-01T00:00:00Z",
    )


def _item(
    repo: str = "r/x",
    item_type: str = "issue",
    item_id: str = "1",
    title: str = "Title",
    summary: str = "Summary.",
    url: str = "https://gh/1",
) -> SummarizedItem:
    return SummarizedItem(
        raw=_raw(repo=repo, item_type=item_type, item_id=item_id, title=title, url=url),
        summary=summary,
    )


def _item_lines(result: str) -> list[str]:
    """Return only the item lines (starting with '- #') from a rendered output."""
    return [line for line in result.splitlines() if line.startswith("- #")]


# ---------------------------------------------------------------------------
# AC-5-015: empty title omits the quoted title
# ---------------------------------------------------------------------------


class TestEmptyTitle:
    def test_empty_title_omits_quoted_segment_ac_5_015(self) -> None:
        """Empty title omits the quoted-title segment (AC-5-015)."""
        item = SummarizedItem(
            raw=_raw(item_id="1", title="", url="https://gh/1"),
            summary="A summary.",
        )
        result = render([item], lookback_days=7)
        assert "- #1 — A summary. [link](https://gh/1)" in result

    def test_empty_title_no_empty_quotes_ac_5_015(self) -> None:
        """Empty title does not produce empty quotes in the line (AC-5-015)."""
        item = SummarizedItem(raw=_raw(item_id="1", title="", url="https://gh/1"), summary="S.")
        result = render([item], lookback_days=7)
        assert '""' not in result


# ---------------------------------------------------------------------------
# AC-5-016: empty url omits the link suffix
# ---------------------------------------------------------------------------


class TestEmptyUrl:
    def test_empty_url_omits_link_suffix_ac_5_016(self) -> None:
        """Empty url omits the [link](...) segment (AC-5-016)."""
        item = SummarizedItem(
            raw=_raw(item_id="1", title="T", url=""),
            summary="S.",
        )
        result = render([item], lookback_days=7)
        assert '- #1 "T" — S.' in result
        assert "[link]" not in result

    def test_empty_url_no_empty_link_ac_5_016(self) -> None:
        """Empty url does not produce a [link]() with empty parens (AC-5-016)."""
        item = SummarizedItem(raw=_raw(item_id="1", title="T", url=""), summary="S.")
        result = render([item], lookback_days=7)
        assert "[link]()" not in result


# ---------------------------------------------------------------------------
# AC-5-017: empty/whitespace summary omits the summary segment
# ---------------------------------------------------------------------------


class TestEmptySummary:
    def test_empty_summary_omits_summary_segment_ac_5_017(self) -> None:
        """Empty summary omits the '— summary' segment (AC-5-017)."""
        item = SummarizedItem(
            raw=_raw(item_id="1", title="T", url="https://gh/1"),
            summary="",
        )
        result = render([item], lookback_days=7)
        # The item line must not contain an em-dash; check only the item line
        # (repo header also uses em-dash so we inspect only the item lines)
        assert '- #1 "T" [link](https://gh/1)' in result
        lines = _item_lines(result)
        assert len(lines) == 1
        assert "—" not in lines[0]  # U+2014 em-dash

    def test_whitespace_only_summary_omits_segment_ac_5_017(self) -> None:
        """Whitespace-only summary omits the '— summary' segment (AC-5-017)."""
        item = SummarizedItem(raw=_raw(item_id="1", title="T", url="https://gh/1"), summary="   ")
        result = render([item], lookback_days=7)
        lines = _item_lines(result)
        assert len(lines) == 1
        assert "—" not in lines[0]  # U+2014 em-dash

    def test_whitespace_summary_renders_original_not_stripped_ac_5_017(self) -> None:
        """Non-whitespace summary is rendered as-is (not stripped internally) (AC-5-017)."""
        # Only the OMIT decision uses .strip(); the rendered text is the original.
        item = SummarizedItem(
            raw=_raw(item_id="1", title="T", url="https://x"),
            summary="  spaces  ",
        )
        result = render([item], lookback_days=7)
        # Segment was non-empty after strip() so it IS rendered, with original whitespace
        assert "—   spaces  " in result


# ---------------------------------------------------------------------------
# AC-5-018: all-empty fields except item_id renders at least - #{item_id} (EC-002)
# ---------------------------------------------------------------------------


class TestAllEmptyFields:
    def test_all_empty_except_id_renders_id_line_ac_5_018(self) -> None:
        """All-empty fields except item_id renders '- #1' without raising (AC-5-018, EC-002)."""
        item = SummarizedItem(raw=_raw(item_id="1", title="", url=""), summary="")
        result = render([item], lookback_days=7)
        assert "- #1" in result

    def test_all_empty_fields_does_not_raise_ac_5_018(self) -> None:
        """Rendering all-empty fields raises no exception (AC-5-018)."""
        item = SummarizedItem(raw=_raw(item_id="99", title="", url=""), summary="")
        result = render([item], lookback_days=7)
        assert "- #99" in result

    def test_all_empty_fields_line_is_exactly_id_only_ac_5_018(self) -> None:
        """All-empty fields line is exactly '- #{item_id}' with no trailing content (AC-5-018)."""
        item = SummarizedItem(raw=_raw(item_id="5", title="", url=""), summary="")
        result = render([item], lookback_days=7)
        lines = _item_lines(result)
        assert len(lines) == 1
        assert lines[0] == "- #5"


# ---------------------------------------------------------------------------
# AC-5-019: unknown item_type is bucketed under "Khác" (EC-011)
# ---------------------------------------------------------------------------


class TestUnknownItemTypeBucketing:
    def test_unknown_type_renders_under_khac_ac_5_019(self) -> None:
        """An unknown item_type renders under '### Khác (1)' (AC-5-019, EC-011)."""
        item = _item(item_type="commit", item_id="7")
        result = render([item], lookback_days=7)
        assert "### Khác (1)" in result
        assert "- #7" in result

    def test_unknown_type_appears_after_known_types_ac_5_019(self) -> None:
        """Khác group appears after all known-type groups (AC-5-019)."""
        items = [
            _item(item_type="issue", item_id="1"),
            _item(item_type="commit", item_id="2"),
        ]
        result = render(items, lookback_days=7)
        issue_pos = result.index("### Issue mới")
        khac_pos = result.index("### Khác")
        assert issue_pos < khac_pos

    def test_unknown_type_not_in_known_groups_ac_5_019(self) -> None:
        """An unknown item_type does NOT appear under a known group header (AC-5-019)."""
        item = _item(item_type="commit", item_id="9")
        result = render([item], lookback_days=7)
        assert "### Issue mới" not in result
        assert "### Discussion" not in result
        assert "### Release" not in result


# ---------------------------------------------------------------------------
# AC-5-020: every input item appears exactly once (EC-009 duplicate item_id)
# ---------------------------------------------------------------------------


class TestEveryItemRenderedOnce:
    def test_n_items_produce_n_item_lines_ac_5_020(self) -> None:
        """N input items produce exactly N item lines in output (AC-5-020)."""
        items = [_item(repo="r/x", item_type="issue", item_id=str(i)) for i in range(5)]
        result = render(items, lookback_days=7)
        lines = _item_lines(result)
        assert len(lines) == 5

    def test_duplicate_item_id_both_rendered_ec_009(self) -> None:
        """Duplicate item_id: both lines rendered (renderer does not dedupe) (AC-5-020, EC-009)."""
        items = [
            _item(item_id="123", summary="First."),
            _item(item_id="123", summary="Second."),
        ]
        result = render(items, lookback_days=7)
        lines = _item_lines(result)
        assert len(lines) == 2
        assert "### Issue mới (2)" in result

    def test_mixed_repos_and_types_count_ac_5_020(self) -> None:
        """Mixed repos and types: total item lines equals total input items (AC-5-020)."""
        items = [
            _item(repo="a/a", item_type="issue", item_id="1"),
            _item(repo="a/a", item_type="release", item_id="2"),
            _item(repo="b/b", item_type="discussion", item_id="3"),
            _item(repo="b/b", item_type="commit", item_id="4"),  # unknown type
        ]
        result = render(items, lookback_days=7)
        lines = _item_lines(result)
        assert len(lines) == 4


# ---------------------------------------------------------------------------
# EC-005: markdown-special / non-ASCII rendered as-is (A-A4)
# ---------------------------------------------------------------------------


class TestMarkdownSpecialAndNonAscii:
    def test_markdown_special_chars_rendered_as_is_ec_005(self) -> None:
        """Markdown-special chars in title/summary are rendered verbatim (EC-005, A-A4)."""
        item = SummarizedItem(
            raw=_raw(item_id="1", title="**bold** [link]", url="https://x"),
            summary="Use `backtick` and _italic_.",
        )
        result = render([item], lookback_days=7)
        assert "**bold** [link]" in result
        assert "`backtick`" in result

    def test_non_ascii_emoji_rendered_as_is_ec_005(self) -> None:
        """Non-ASCII and emoji chars are rendered without crashing (EC-005)."""
        item = SummarizedItem(
            raw=_raw(item_id="1", title="Fix typo in README", url="https://x"),
            summary="Fixes Vietnamese: không, thêm.",
        )
        result = render([item], lookback_days=7)
        assert "không" in result
        assert "thêm" in result
