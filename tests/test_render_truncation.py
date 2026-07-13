"""Tests for truncation alert in render() (AC-V4-002-007, AC-V4-002-012)."""

from osspulse.models import RawItem, SummarizedItem
from osspulse.render.renderer import render

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(
    repo: str = "org/repo-a",
    item_type: str = "issue",
    idx: int = 1,
    summary: str = "A summary.",
) -> SummarizedItem:
    raw = RawItem(
        repo=repo,
        item_type=item_type,
        item_id=str(idx),
        title=f"Item {idx}",
        body=f"Body {idx}",
        url=f"https://github.com/{repo}/issues/{idx}",
        created_at="2026-06-01T00:00:00Z",
    )
    return SummarizedItem(raw=raw, summary=summary)


# ---------------------------------------------------------------------------
# AC-V4-002-007 — truncation alert line emitted when dropped > 0
# ---------------------------------------------------------------------------


def test_truncation_alert_emitted_when_dropped(AC="AC-V4-002-007"):
    """dropped_counts with 5 drops → '⚠️ +5 items not shown (limit: 10)' line (AC-V4-002-007)."""
    items = [_item(idx=i) for i in range(1, 6)]
    dropped_counts = {"org/repo-a": {"issue": 5}}
    output = render(items, lookback_days=7, dropped_counts=dropped_counts, max_items_per_type=10)

    assert "⚠️ +5 items not shown (limit: 10)" in output


def test_truncation_alert_format_exact(AC="AC-V4-002-007"):
    """Alert line exactly matches the locked AC spec format (AC-V4-002-007)."""
    items = [_item(idx=1)]
    dropped_counts = {"org/repo-a": {"issue": 3}}
    output = render(items, lookback_days=7, dropped_counts=dropped_counts, max_items_per_type=5)

    assert "⚠️ +3 items not shown (limit: 5)" in output


def test_truncation_alert_placed_after_repo_header(AC="AC-V4-002-007"):
    """Alert line appears immediately after the ## repo header (ADR-002)."""
    items = [_item(idx=1)]
    dropped_counts = {"org/repo-a": {"issue": 2}}
    output = render(items, lookback_days=7, dropped_counts=dropped_counts, max_items_per_type=10)

    lines = output.splitlines()
    header_idx = next(i for i, ln in enumerate(lines) if ln.startswith("## org/repo-a"))
    alert_idx = next(i for i, ln in enumerate(lines) if "⚠️" in ln)
    assert alert_idx == header_idx + 1


def test_truncation_alert_aggregates_across_types(AC="AC-V4-002-007"):
    """Alert count is the sum across all item_types for the repo."""
    items = [_item(idx=1, item_type="issue"), _item(idx=2, item_type="release")]
    dropped_counts = {"org/repo-a": {"issue": 3, "release": 2}}
    output = render(items, lookback_days=7, dropped_counts=dropped_counts, max_items_per_type=10)

    # Total drops = 5
    assert "⚠️ +5 items not shown (limit: 10)" in output


def test_no_alert_for_repo_with_zero_drops(AC="AC-V4-002-007"):
    """Repo with 0 drops gets no alert line (off-by-one guard, AC-V4-002-007)."""
    items = [_item(idx=1)]
    # dropped_counts has no entry for this repo
    dropped_counts = {"org/other-repo": {"issue": 2}}
    output = render(items, lookback_days=7, dropped_counts=dropped_counts, max_items_per_type=10)

    assert "⚠️" not in output


def test_only_repos_with_drops_get_alert():
    """Multi-repo: only repos in dropped_counts get an alert (AC-V4-002-007)."""
    items = [
        _item(repo="org/repo-a", idx=1),
        _item(repo="org/repo-b", idx=2),
    ]
    dropped_counts = {"org/repo-a": {"issue": 5}}  # repo-b has no drops
    output = render(items, lookback_days=7, dropped_counts=dropped_counts, max_items_per_type=10)

    lines = output.splitlines()
    # Find repo-b header
    repo_b_idx = next(i for i, ln in enumerate(lines) if ln.startswith("## org/repo-b"))
    # The line after repo-b header should NOT be an alert
    if repo_b_idx + 1 < len(lines):
        assert "⚠️" not in lines[repo_b_idx + 1]


# ---------------------------------------------------------------------------
# AC-V4-002-012 — byte-identical no-op when no truncation
# ---------------------------------------------------------------------------


def test_byte_identical_when_no_dropped_counts(AC="AC-V4-002-012"):
    """render() with dropped_counts=None is byte-identical to call without the param."""
    items = [_item(idx=1), _item(idx=2)]

    baseline = render(items, lookback_days=7)
    with_none = render(items, lookback_days=7, dropped_counts=None, max_items_per_type=None)

    assert baseline == with_none


def test_byte_identical_when_empty_dropped_counts(AC="AC-V4-002-012"):
    """render() with dropped_counts={} is byte-identical to baseline (AC-V4-002-012)."""
    items = [_item(idx=1)]

    baseline = render(items, lookback_days=7)
    with_empty = render(items, lookback_days=7, dropped_counts={}, max_items_per_type=10)

    assert baseline == with_empty


def test_byte_identical_no_items(AC="AC-V4-002-012"):
    """Empty items with None dropped_counts → byte-identical no-new-items doc."""
    baseline = render([], lookback_days=7)
    with_none = render([], lookback_days=7, dropped_counts=None, max_items_per_type=None)

    assert baseline == with_none


def test_no_alert_when_max_items_per_type_is_none(AC="AC-V4-002-012"):
    """dropped_counts provided but max_items_per_type=None → no alert line emitted."""
    items = [_item(idx=1)]
    dropped_counts = {"org/repo-a": {"issue": 5}}
    output = render(items, lookback_days=7, dropped_counts=dropped_counts, max_items_per_type=None)

    # max_items_per_type is None → the guard short-circuits, no alert
    assert "⚠️" not in output
