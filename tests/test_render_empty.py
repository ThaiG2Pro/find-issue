"""Empty-input and empty-section tests for the Digest Renderer (AC-5-008..011, EC-001/015).

Rules:
- All test names carry their AC-ID (R3).
- Pure function — no mocks needed.
"""

from osspulse.models import RawItem, SummarizedItem
from osspulse.render import render

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(
    repo: str = "owner/repo",
    item_type: str = "issue",
    item_id: str = "1",
    title: str = "Title",
    summary: str = "Summary.",
    url: str = "https://gh/1",
) -> SummarizedItem:
    raw = RawItem(
        repo=repo,
        item_type=item_type,
        item_id=item_id,
        title=title,
        body="",
        url=url,
        created_at="2024-01-01T00:00:00Z",
    )
    return SummarizedItem(raw=raw, summary=summary)


# ---------------------------------------------------------------------------
# AC-5-008 + AC-5-009: empty list returns a non-empty "No new items" doc (EC-001)
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_input_returns_nonempty_string_ac_5_008(self) -> None:
        """Empty list returns a non-empty string (AC-5-008, EC-001)."""
        result = render([], lookback_days=7)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_input_contains_no_new_items_message_ac_5_008(self) -> None:
        """Empty list result contains the 'No new items' message (AC-5-008)."""
        result = render([], lookback_days=7)
        assert "No new items in the last 7 days" in result

    def test_empty_input_contains_title_ac_5_008(self) -> None:
        """Empty list result contains the top-level title (AC-5-008)."""
        result = render([], lookback_days=7)
        assert "# OSS Pulse Digest" in result

    def test_empty_input_has_no_repo_sections_ac_5_008(self) -> None:
        """Empty list result has no ## repo sections (AC-5-008)."""
        result = render([], lookback_days=7)
        assert "## " not in result

    def test_empty_input_message_reflects_lookback_days_ac_5_008(self) -> None:
        """No new items message reflects the lookback_days parameter (AC-5-008)."""
        result = render([], lookback_days=30)
        assert "No new items in the last 30 days" in result

    def test_empty_input_strip_nonempty_ac_5_009(self) -> None:
        """Empty list result is not empty or whitespace-only (AC-5-009)."""
        result = render([], lookback_days=7)
        assert result.strip()

    def test_empty_input_not_empty_string_ac_5_009(self) -> None:
        """Empty list result is not the empty string (AC-5-009)."""
        result = render([], lookback_days=7)
        assert result != ""


# ---------------------------------------------------------------------------
# AC-5-010: a repo with no items produces no section (EC-015)
# ---------------------------------------------------------------------------


class TestRepoWithNoItems:
    def test_absent_repo_has_no_section_ac_5_010(self) -> None:
        """A repo not in the items list produces no ## section (AC-5-010, EC-015)."""
        result = render([_item(repo="alpha/a")], lookback_days=7)
        assert "## alpha/a" in result
        assert "## zeta/b" not in result

    def test_only_repos_with_items_are_rendered_ac_5_010(self) -> None:
        """Only repos that appear in items get a ## section (AC-5-010)."""
        items = [_item(repo="present/repo")]
        result = render(items, lookback_days=7)
        section_headers = [line for line in result.splitlines() if line.startswith("## ")]
        assert len(section_headers) == 1
        assert "## present/repo" in result


# ---------------------------------------------------------------------------
# AC-5-011: an item type with no items produces no group header
# ---------------------------------------------------------------------------


class TestGroupWithNoItems:
    def test_empty_item_type_has_no_group_header_ac_5_011(self) -> None:
        """A repo with only issues has no Discussion or Release headers (AC-5-011)."""
        result = render([_item(repo="r/x", item_type="issue")], lookback_days=7)
        assert "### Issue mới" in result
        assert "### Discussion" not in result
        assert "### Release" not in result

    def test_only_present_groups_are_rendered_ac_5_011(self) -> None:
        """Only groups that have items get a ### header (AC-5-011)."""
        items = [_item(repo="r/x", item_type="discussion")]
        result = render(items, lookback_days=7)
        group_headers = [line for line in result.splitlines() if line.startswith("### ")]
        assert len(group_headers) == 1
        assert "### Discussion (1)" in result
