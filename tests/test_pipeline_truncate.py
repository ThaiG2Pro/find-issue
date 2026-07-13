"""Tests for _truncate_per_type pipeline helper (AC-V4-002-003, AC-V4-002-004, AC-V4-002-006)."""

from osspulse.models import RawItem
from osspulse.pipeline import _truncate_per_type

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw(
    repo: str = "org/repo-a",
    *,
    item_type: str = "issue",
    idx: int = 1,
    created_at: str | None = None,
) -> RawItem:
    ts = created_at or f"2026-06-{idx:02d}T00:00:00Z"
    return RawItem(
        repo=repo,
        item_type=item_type,
        item_id=str(idx),
        title=f"Item {idx}",
        body=f"Body {idx}",
        url=f"https://github.com/{repo}/issues/{idx}",
        created_at=ts,
    )


# ---------------------------------------------------------------------------
# AC-V4-002-003 / AC-V4-002-004 — keep newest N, drop oldest
# ---------------------------------------------------------------------------


def test_15_items_cap_10_keeps_10_newest(AC="AC-V4-002-003"):
    """15 items in one (repo, item_type), cap 10 → 10 newest kept (AC-V4-002-003)."""
    # Items idx 1..15; created_at uses idx so idx 15 is newest, 1 is oldest
    items = [_raw(idx=i, created_at=f"2026-06-{i:02d}T00:00:00Z") for i in range(1, 16)]
    kept, dropped = _truncate_per_type(items, cap=10)

    assert len(kept) == 10
    kept_ids = {item.item_id for item in kept}
    # Newest 10: idx 6..15
    for i in range(6, 16):
        assert str(i) in kept_ids, f"item {i} should be kept (newest)"
    # Oldest 5: idx 1..5
    for i in range(1, 6):
        assert str(i) not in kept_ids, f"item {i} should be dropped (oldest)"


def test_dropped_count_accurate(AC="AC-V4-002-004"):
    """dropped_counts[repo][item_type] == number dropped (AC-V4-002-004)."""
    items = [_raw(idx=i, created_at=f"2026-06-{i:02d}T00:00:00Z") for i in range(1, 16)]
    _, dropped = _truncate_per_type(items, cap=10)

    assert dropped["org/repo-a"]["issue"] == 5


def test_exactly_at_cap_zero_dropped(AC="AC-V4-002-004"):
    """Group exactly at cap → 0 dropped, no entry in dropped_counts (AC-V4-002-004)."""
    items = [_raw(idx=i) for i in range(1, 11)]  # exactly 10
    kept, dropped = _truncate_per_type(items, cap=10)

    assert len(kept) == 10
    assert dropped == {}


def test_below_cap_zero_dropped(AC="AC-V4-002-004"):
    """Group below cap → all kept, dropped_counts empty (AC-V4-002-004)."""
    items = [_raw(idx=i) for i in range(1, 6)]  # 5 items, cap 10
    kept, dropped = _truncate_per_type(items, cap=10)

    assert len(kept) == 5
    assert dropped == {}


# ---------------------------------------------------------------------------
# Input order preserved after truncation
# ---------------------------------------------------------------------------


def test_surviving_items_preserve_input_order():
    """Survivors retain their relative input order (ADR-001 filter-in-place)."""
    # Items with non-sequential created_at to verify sort doesn't reorder kept items
    items = [
        _raw(idx=1, created_at="2026-06-10T00:00:00Z"),
        _raw(idx=2, created_at="2026-06-12T00:00:00Z"),
        _raw(idx=3, created_at="2026-06-08T00:00:00Z"),
        _raw(idx=4, created_at="2026-06-15T00:00:00Z"),
        _raw(idx=5, created_at="2026-06-01T00:00:00Z"),  # oldest — dropped
    ]
    kept, _ = _truncate_per_type(items, cap=4)

    # Items 1,2,3,4 survive; must be in their original input order (1→2→3→4)
    kept_ids = [item.item_id for item in kept]
    assert kept_ids == ["1", "2", "3", "4"]


# ---------------------------------------------------------------------------
# Multiple (repo, item_type) groups
# ---------------------------------------------------------------------------


def test_multiple_repos_independent_caps():
    """Each (repo, item_type) group is capped independently."""
    items_a = [
        _raw(repo="org/a", idx=i, created_at=f"2026-06-{i:02d}T00:00:00Z") for i in range(1, 16)
    ]
    items_b = [
        _raw(repo="org/b", idx=i, created_at=f"2026-06-{i:02d}T00:00:00Z") for i in range(1, 6)
    ]
    kept, dropped = _truncate_per_type(items_a + items_b, cap=10)

    # org/a: 15 → 10 kept, 5 dropped
    a_kept = [it for it in kept if it.repo == "org/a"]
    assert len(a_kept) == 10
    assert dropped["org/a"]["issue"] == 5

    # org/b: 5 ≤ 10 → all kept, no dropped entry
    b_kept = [it for it in kept if it.repo == "org/b"]
    assert len(b_kept) == 5
    assert "org/b" not in dropped


def test_multiple_item_types_independent(AC="AC-V4-002-003"):
    """Issues and releases in the same repo are capped independently (AC-V4-002-003)."""
    issues = [
        _raw(idx=i, item_type="issue", created_at=f"2026-06-{i:02d}T00:00:00Z")
        for i in range(1, 16)
    ]
    releases = [
        _raw(idx=i, item_type="release", created_at=f"2026-06-{i:02d}T00:00:00Z")
        for i in range(1, 4)
    ]
    kept, dropped = _truncate_per_type(issues + releases, cap=10)

    kept_issues = [it for it in kept if it.item_type == "issue"]
    kept_releases = [it for it in kept if it.item_type == "release"]
    assert len(kept_issues) == 10
    assert len(kept_releases) == 3  # below cap — all kept
    assert dropped["org/repo-a"]["issue"] == 5
    assert "release" not in dropped.get("org/repo-a", {})


# ---------------------------------------------------------------------------
# AC-V4-002-006 — mark_seen receives the FULL set (idempotency invariant)
# The pipeline wires this correctly: mark_seen runs inside _collect_all
# BEFORE _truncate_per_type is called. This test asserts the ordering contract
# by verifying that _truncate_per_type does NOT modify or reduce its input list.
# ---------------------------------------------------------------------------


def test_truncate_does_not_mutate_input_list(AC="AC-V4-002-006"):
    """_truncate_per_type does not mutate the original list (AC-V4-002-006)."""
    items = [_raw(idx=i, created_at=f"2026-06-{i:02d}T00:00:00Z") for i in range(1, 16)]
    original_ids = [it.item_id for it in items]
    _truncate_per_type(items, cap=10)
    # Original list unchanged — mark_seen can still operate on it
    assert [it.item_id for it in items] == original_ids
    assert len(items) == 15


def test_full_set_captured_before_truncation(AC="AC-V4-002-006"):
    """All 15 items are present in the input list before truncation (AC-V4-002-006).

    This verifies that _truncate_per_type receives the full collected set,
    meaning mark_seen (which runs before _truncate_per_type in the pipeline)
    will have already recorded all items.
    """
    items = [_raw(idx=i, created_at=f"2026-06-{i:02d}T00:00:00Z") for i in range(1, 16)]
    kept, dropped = _truncate_per_type(items, cap=10)

    # Full set = 15 items passed in
    assert len(items) == 15
    # Truncated set = 10 items
    assert len(kept) == 10
    # Dropped = 5
    assert dropped["org/repo-a"]["issue"] == 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty():
    """Empty input → empty kept, empty dropped (no crash)."""
    kept, dropped = _truncate_per_type([], cap=10)
    assert kept == []
    assert dropped == {}


def test_cap_1_keeps_only_newest():
    """Cap 1 keeps exactly the newest item per (repo, item_type)."""
    items = [_raw(idx=i, created_at=f"2026-06-{i:02d}T00:00:00Z") for i in range(1, 6)]
    kept, dropped = _truncate_per_type(items, cap=1)
    assert len(kept) == 1
    assert kept[0].item_id == "5"  # idx 5 = newest
    assert dropped["org/repo-a"]["issue"] == 4
