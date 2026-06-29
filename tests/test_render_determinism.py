"""Determinism tests for the Digest Renderer (AC-5-004..007, EC-006..008, EC-014).

Rules:
- All test names carry their AC-ID (R3).
- Pure function — no mocks needed.
"""

import random

from osspulse.models import RawItem, SummarizedItem
from osspulse.render import render

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(
    repo: str = "owner/repo",
    item_type: str = "issue",
    item_id: str = "1",
    title: str = "A title",
    summary: str = "A summary.",
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


def _item_lines(result: str) -> list[str]:
    """Return only the item lines (starting with '- #') from a rendered output."""
    return [line for line in result.splitlines() if line.startswith("- #")]


# ---------------------------------------------------------------------------
# AC-5-004: double render yields byte-equal output (EC-006)
# ---------------------------------------------------------------------------


class TestDoubleRenderIdempotent:
    def test_double_render_byte_equal_ac_5_004(self) -> None:
        """Same input rendered twice produces byte-for-byte identical output (AC-5-004, EC-006)."""
        items = [
            _item(repo="alpha/a", item_id="1"),
            _item(repo="zeta/b", item_type="release", item_id="2"),
        ]
        first = render(items, lookback_days=7)
        second = render(items, lookback_days=7)
        assert first == second

    def test_double_render_byte_equal_empty_input_ac_5_004(self) -> None:
        """Double render of empty input is also byte-equal (AC-5-004)."""
        assert render([], lookback_days=7) == render([], lookback_days=7)


# ---------------------------------------------------------------------------
# AC-5-005: repos ordered alphabetically regardless of input order (EC-007)
# ---------------------------------------------------------------------------


class TestRepoAlphabeticalOrder:
    def test_repos_ordered_alphabetically_ac_5_005(self) -> None:
        """alpha/a appears before zeta/b regardless of input order (AC-5-005)."""
        items = [
            _item(repo="zeta/b", item_id="2"),
            _item(repo="alpha/a", item_id="1"),
        ]
        result = render(items, lookback_days=7)
        alpha_pos = result.index("## alpha/a")
        zeta_pos = result.index("## zeta/b")
        assert alpha_pos < zeta_pos

    def test_shuffled_input_produces_identical_output_ac_5_005(self) -> None:
        """Shuffled repo input order produces the same output (AC-5-005, EC-007)."""
        items = [
            _item(repo="zeta/b", item_id="2"),
            _item(repo="alpha/a", item_id="1"),
            _item(repo="mid/c", item_id="3"),
        ]
        canonical = render(items, lookback_days=7)

        shuffled = items[:]
        random.seed(42)
        random.shuffle(shuffled)
        assert render(shuffled, lookback_days=7) == canonical

    def test_case_insensitive_sort_ac_5_005(self) -> None:
        """Repo sort is case-insensitive: 'Alpha/A' sorts before 'zeta/b' (AC-5-005)."""
        items = [
            _item(repo="zeta/b", item_id="2"),
            _item(repo="Alpha/A", item_id="1"),
        ]
        result = render(items, lookback_days=7)
        assert result.index("## Alpha/A") < result.index("## zeta/b")


# ---------------------------------------------------------------------------
# AC-5-006: item-type groups in fixed Issues→Discussions→Releases order (EC-014)
# ---------------------------------------------------------------------------


class TestGroupOrder:
    def test_group_order_issues_before_discussions_before_releases_ac_5_006(self) -> None:
        """Groups appear in fixed Issues→Discussions→Releases order (AC-5-006)."""
        items = [
            _item(repo="r/x", item_type="release", item_id="3"),
            _item(repo="r/x", item_type="issue", item_id="1"),
            _item(repo="r/x", item_type="discussion", item_id="2"),
        ]
        result = render(items, lookback_days=7)
        issue_pos = result.index("### Issue mới")
        disc_pos = result.index("### Discussion")
        rel_pos = result.index("### Release")
        assert issue_pos < disc_pos < rel_pos

    def test_all_known_types_plus_unknown_order_ec_014(self) -> None:
        """All three known types + one unknown render Issues→Discussions→Releases→Khác (EC-014)."""
        items = [
            _item(repo="r/x", item_type="commit", item_id="4"),
            _item(repo="r/x", item_type="release", item_id="3"),
            _item(repo="r/x", item_type="issue", item_id="1"),
            _item(repo="r/x", item_type="discussion", item_id="2"),
        ]
        result = render(items, lookback_days=7)
        issue_pos = result.index("### Issue mới")
        disc_pos = result.index("### Discussion")
        rel_pos = result.index("### Release")
        other_pos = result.index("### Khác")
        assert issue_pos < disc_pos < rel_pos < other_pos


# ---------------------------------------------------------------------------
# AC-5-007: items within a group preserve input order (EC-008)
# ---------------------------------------------------------------------------


class TestWithinGroupInputOrderPreserved:
    def test_within_group_order_preserved_ac_5_007(self) -> None:
        """Items within a group appear in input order (#123 before #120) (AC-5-007)."""
        items = [
            _item(repo="r/x", item_id="123"),
            _item(repo="r/x", item_id="120"),
        ]
        result = render(items, lookback_days=7)
        pos_123 = result.index("- #123")
        pos_120 = result.index("- #120")
        assert pos_123 < pos_120

    def test_within_group_order_not_re_sorted_ac_5_007(self) -> None:
        """Items with higher id appearing first in input stay first in output (AC-5-007, EC-008)."""
        # Ids in descending order — renderer must NOT sort them
        items = [_item(repo="r/x", item_id=str(i)) for i in [9, 1, 5, 3]]
        result = render(items, lookback_days=7)
        lines = _item_lines(result)
        # Extract the item_id token (second whitespace-separated token, e.g. "#9")
        ids_in_output = [line.split()[1] for line in lines]
        assert ids_in_output == ["#9", "#1", "#5", "#3"]
