"""Happy-path and format tests for the Digest Renderer (AC-5-001, AC-5-012..014).

Rules:
- All test names carry their AC-ID (R3).
- No mocks needed — the renderer is a pure function.
"""

from osspulse.models import RawItem, SummarizedItem
from osspulse.render import MarkdownDigestRenderer, render

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw(
    repo: str = "owner/repo",
    item_type: str = "issue",
    item_id: str = "1",
    title: str = "A title",
    body: str = "body text",
    url: str = "https://gh/1",
    created_at: str = "2024-01-01T00:00:00Z",
) -> RawItem:
    return RawItem(
        repo=repo,
        item_type=item_type,
        item_id=item_id,
        title=title,
        body=body,
        url=url,
        created_at=created_at,
    )


def _item(
    repo: str = "owner/repo",
    item_type: str = "issue",
    item_id: str = "1",
    title: str = "A title",
    summary: str = "A summary.",
    url: str = "https://gh/1",
) -> SummarizedItem:
    return SummarizedItem(
        raw=_raw(repo=repo, item_type=item_type, item_id=item_id, title=title, url=url),
        summary=summary,
    )


# ---------------------------------------------------------------------------
# AC-5-001: non-empty list renders to non-empty str with ## per repo + - #id lines
# ---------------------------------------------------------------------------


class TestNonEmptyRenderStructure:
    def test_returns_string_type_ac_5_001(self) -> None:
        """Non-empty input produces a str result (AC-5-001)."""
        result = render([_item()], lookback_days=7)
        assert isinstance(result, str)

    def test_result_is_nonempty_ac_5_001(self) -> None:
        """Non-empty input produces a non-empty str (AC-5-001)."""
        result = render([_item()], lookback_days=7)
        assert result.strip()

    def test_contains_repo_section_header_ac_5_001(self) -> None:
        """Output contains a ## section for each repo present (AC-5-001)."""
        result = render([_item(repo="alpha/a")], lookback_days=7)
        assert "## alpha/a" in result

    def test_contains_item_line_ac_5_001(self) -> None:
        """Output contains a - #id line for each item (AC-5-001)."""
        result = render([_item(item_id="42")], lookback_days=7)
        assert "- #42" in result

    def test_contains_top_title_ac_5_001(self) -> None:
        """Output starts with the top-level title (AC-5-001)."""
        result = render([_item()], lookback_days=7)
        assert result.startswith("# OSS Pulse Digest")

    def test_adapter_class_returns_same_as_free_function_ac_5_001(self) -> None:
        """MarkdownDigestRenderer.render() matches free function output (AC-5-001)."""
        items = [_item(repo="r/x", item_id="99")]
        assert MarkdownDigestRenderer().render(items, lookback_days=7) == render(
            items, lookback_days=7
        )


# ---------------------------------------------------------------------------
# AC-5-012: canonical line byte-match
# ---------------------------------------------------------------------------


class TestCanonicalLineFormat:
    def test_canonical_line_byte_match_ac_5_012(self) -> None:
        """Full item line matches exact spec bytes (AC-5-012)."""
        item = SummarizedItem(
            raw=_raw(item_id="123", title="Fix bug", url="https://gh/123"),
            summary="Handle null pointer.",
        )
        result = render([item], lookback_days=7)
        assert '- #123 "Fix bug" — Handle null pointer. [link](https://gh/123)' in result

    def test_canonical_line_uses_em_dash_not_hyphen_ac_5_012(self) -> None:
        """Summary segment uses em-dash U+2014, not a hyphen (AC-5-012)."""
        item = SummarizedItem(raw=_raw(item_id="1", title="T", url="https://x"), summary="S.")
        result = render([item], lookback_days=7)
        assert "— S." in result
        # em-dash U+2014, not ASCII hyphen
        assert "—" in result


# ---------------------------------------------------------------------------
# AC-5-013: repo header format
# ---------------------------------------------------------------------------


class TestRepoHeaderFormat:
    def test_repo_header_exact_format_ac_5_013(self) -> None:
        """Repo header is exactly '## {repo} — {lookback_days} ngày qua' (AC-5-013)."""
        result = render([_item(repo="alpha/a")], lookback_days=7)
        assert "## alpha/a — 7 ngày qua" in result

    def test_repo_header_reflects_lookback_days_ac_5_013(self) -> None:
        """Lookback days is reflected in the repo header (AC-5-013)."""
        result = render([_item(repo="org/repo")], lookback_days=30)
        assert "## org/repo — 30 ngày qua" in result


# ---------------------------------------------------------------------------
# AC-5-014: group header format and count
# ---------------------------------------------------------------------------


class TestGroupHeaderFormat:
    def test_group_header_issue_count_3_ac_5_014(self) -> None:
        """Issue group header shows correct count (AC-5-014)."""
        items = [_item(repo="r/x", item_id=str(i)) for i in range(3)]
        result = render(items, lookback_days=7)
        assert "### Issue mới (3)" in result

    def test_group_header_discussion_label_ac_5_014(self) -> None:
        """Discussion group uses label 'Discussion' (AC-5-014)."""
        item = _item(repo="r/x", item_type="discussion", item_id="1")
        result = render([item], lookback_days=7)
        assert "### Discussion (1)" in result

    def test_group_header_release_label_ac_5_014(self) -> None:
        """Release group uses label 'Release' (AC-5-014)."""
        item = _item(repo="r/x", item_type="release", item_id="1")
        result = render([item], lookback_days=7)
        assert "### Release (1)" in result
