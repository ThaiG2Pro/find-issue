"""Unit tests for GitHubCollector._map_discussion (AC-V2-006-005..010).

Tests every field-mapping + null/missing case. No HTTP calls needed — _map_discussion
is a pure data transformer that takes a dict and returns a RawItem or None.
"""

import httpx

from osspulse.github import CollectorConfig, GitHubCollector
from osspulse.models import RawItem

# ---------------------------------------------------------------------------
# Fixture — a collector instance (no real HTTP needed for _map_discussion)
# ---------------------------------------------------------------------------


def _collector() -> GitHubCollector:
    """Build a collector; no transport needed for mapping-only tests."""
    cfg = CollectorConfig()
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])),
        base_url=cfg.base_url,
        headers={"Authorization": "Bearer ghp_fake"},
    )
    return GitHubCollector("ghp_fake", cfg, client=client)


REPO = "org/repo-a"


# ---------------------------------------------------------------------------
# AC-V2-006-005: item_id = str(number)
# ---------------------------------------------------------------------------


def test_item_id_is_stringified_number():
    """item_id is str(number), not the GraphQL node id (AC-V2-006-005)."""
    col = _collector()
    node = {
        "number": 42,
        "title": "T",
        "body": "B",
        "url": "https://example.com",
        "createdAt": "2026-07-01T00:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.item_id == "42"
    assert item.item_type == "discussion"
    assert item.repo == REPO


def test_item_id_number_1():
    """item_id works for number=1 (AC-V2-006-005)."""
    col = _collector()
    node = {
        "number": 1,
        "title": "First",
        "body": "",
        "url": "",
        "createdAt": "2026-07-01T00:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.item_id == "1"


# ---------------------------------------------------------------------------
# AC-V2-006-006: title — normal and null
# ---------------------------------------------------------------------------


def test_title_mapped():
    """Title is mapped from the node (AC-V2-006-006)."""
    col = _collector()
    node = {
        "number": 10,
        "title": "RFC: Improve API",
        "body": "",
        "url": "",
        "createdAt": "2026-07-01T00:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.title == "RFC: Improve API"


def test_title_null_becomes_empty_string():
    """Null title → empty string, no crash (AC-V2-006-006)."""
    col = _collector()
    node = {
        "number": 10,
        "title": None,
        "body": "B",
        "url": "",
        "createdAt": "2026-07-01T00:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.title == ""


def test_title_missing_becomes_empty_string():
    """Missing title key → empty string (AC-V2-006-006)."""
    col = _collector()
    node = {"number": 10, "body": "B", "url": "", "createdAt": "2026-07-01T00:00:00Z"}
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.title == ""


# ---------------------------------------------------------------------------
# AC-V2-006-007: body — markdown field, null → ""
# ---------------------------------------------------------------------------


def test_body_maps_markdown_field():
    """body maps the markdown `body` field (not bodyText) (AC-V2-006-007, ADR-004)."""
    col = _collector()
    node = {
        "number": 10,
        "title": "T",
        "body": "## Heading\nSome **markdown**",
        "url": "",
        "createdAt": "2026-07-01T00:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.body == "## Heading\nSome **markdown**"


def test_body_null_becomes_empty_string():
    """Null body → empty string (AC-V2-006-007)."""
    col = _collector()
    node = {
        "number": 10,
        "title": "T",
        "body": None,
        "url": "",
        "createdAt": "2026-07-01T00:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.body == ""


def test_body_missing_becomes_empty_string():
    """Missing body key → empty string (AC-V2-006-007)."""
    col = _collector()
    node = {"number": 10, "title": "T", "url": "", "createdAt": "2026-07-01T00:00:00Z"}
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.body == ""


# ---------------------------------------------------------------------------
# AC-V2-006-008: url — null/missing → ""
# ---------------------------------------------------------------------------


def test_url_mapped():
    """URL is mapped from the node (AC-V2-006-008)."""
    col = _collector()
    node = {
        "number": 10,
        "title": "T",
        "body": "",
        "url": "https://github.com/org/repo-a/discussions/10",
        "createdAt": "2026-07-01T00:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.url == "https://github.com/org/repo-a/discussions/10"


def test_url_null_becomes_empty_string():
    """Null url → empty string (AC-V2-006-008)."""
    col = _collector()
    node = {
        "number": 10,
        "title": "T",
        "body": "",
        "url": None,
        "createdAt": "2026-07-01T00:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.url == ""


def test_url_missing_becomes_empty_string():
    """Missing url key → empty string (AC-V2-006-008)."""
    col = _collector()
    node = {"number": 10, "title": "T", "body": "", "createdAt": "2026-07-01T00:00:00Z"}
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.url == ""


# ---------------------------------------------------------------------------
# AC-V2-006-009: created_at — raw ISO string, never reformatted
# ---------------------------------------------------------------------------


def test_created_at_preserved_as_raw_iso():
    """created_at stores the raw createdAt ISO string unchanged (AC-V2-006-009)."""
    col = _collector()
    raw_ts = "2026-07-01T14:35:22Z"
    node = {"number": 10, "title": "T", "body": "", "url": "", "createdAt": raw_ts}
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.created_at == raw_ts  # not reformatted


# ---------------------------------------------------------------------------
# AC-V2-006-010: node missing `number` → return None (skip)
# ---------------------------------------------------------------------------


def test_missing_number_returns_none():
    """Node without `number` returns None — cannot key the discussion (AC-V2-006-010)."""
    col = _collector()
    node = {"title": "T", "body": "B", "url": "", "createdAt": "2026-07-01T00:00:00Z"}
    assert col._map_discussion(node, REPO) is None


def test_number_none_returns_none():
    """Node with number=None returns None (AC-V2-006-010)."""
    col = _collector()
    node = {
        "number": None,
        "title": "T",
        "body": "B",
        "url": "",
        "createdAt": "2026-07-01T00:00:00Z",
    }
    assert col._map_discussion(node, REPO) is None


# ---------------------------------------------------------------------------
# AC-V2-006-001: item_type is always "discussion"
# ---------------------------------------------------------------------------


def test_item_type_is_discussion():
    """item_type is always 'discussion' (AC-V2-006-001)."""
    col = _collector()
    node = {"number": 5, "title": "T", "body": "B", "url": "", "createdAt": "2026-07-01T00:00:00Z"}
    item = col._map_discussion(node, REPO)
    assert item is not None
    assert item.item_type == "discussion"


# ---------------------------------------------------------------------------
# Full happy-path: all fields present → complete RawItem
# ---------------------------------------------------------------------------


def test_full_node_maps_to_raw_item():
    """All fields present — returns a fully populated RawItem (AC-V2-006-005..009)."""
    col = _collector()
    node = {
        "number": 99,
        "title": "Support question",
        "body": "How do I configure X?",
        "url": "https://github.com/org/repo-a/discussions/99",
        "createdAt": "2026-06-28T12:00:00Z",
    }
    item = col._map_discussion(node, REPO)
    assert item == RawItem(
        repo=REPO,
        item_type="discussion",
        item_id="99",
        title="Support question",
        body="How do I configure X?",
        url="https://github.com/org/repo-a/discussions/99",
        created_at="2026-06-28T12:00:00Z",
    )
