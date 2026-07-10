"""Unit tests for GitHubCollector._map_release (AC-V2-003-006..011).

Tests the field mapping and null/missing guards for the release → RawItem helper.
No HTTP — pure dict → RawItem logic.
"""

from osspulse.github import CollectorConfig, GitHubCollector

REPO = "org/repo"
TOKEN = "ghp_SUPER_SECRET_TOKEN_value"  # noqa: S105


def _collector() -> GitHubCollector:
    """Build a collector without a real httpx client (we only test _map_release)."""
    import httpx

    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    client = httpx.Client(
        transport=transport,
        base_url=CollectorConfig().base_url,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    return GitHubCollector(TOKEN, CollectorConfig(), client=client)


# ---------------------------------------------------------------------------
# AC-V2-003-006: item_id = tag_name
# ---------------------------------------------------------------------------


def test_map_release_item_id_is_tag_name():
    """item_id is the release tag_name (AC-V2-003-006)."""
    collector = _collector()
    raw = {
        "tag_name": "v1.2.0",
        "name": "Release 1.2.0",
        "body": "changelog",
        "html_url": "https://github.com/org/repo/releases/tag/v1.2.0",
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.item_id == "v1.2.0"
    assert item.item_type == "release"
    assert item.repo == REPO


# ---------------------------------------------------------------------------
# AC-V2-003-007: title falls back to tag_name when name is null/empty
# ---------------------------------------------------------------------------


def test_map_release_title_null_falls_back_to_tag_name():
    """title falls back to tag_name when name is null (AC-V2-003-007)."""
    collector = _collector()
    raw = {
        "tag_name": "v2.0.0",
        "name": None,
        "body": "",
        "html_url": "https://github.com/org/repo/releases/tag/v2.0.0",
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.title == "v2.0.0"


def test_map_release_title_empty_string_falls_back_to_tag_name():
    """title falls back to tag_name when name is empty string (AC-V2-003-007)."""
    collector = _collector()
    raw = {
        "tag_name": "v3.0.0",
        "name": "",
        "body": "",
        "html_url": "https://github.com/org/repo/releases/tag/v3.0.0",
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.title == "v3.0.0"


def test_map_release_title_present_is_used():
    """title uses name field when present and non-empty (AC-V2-003-007)."""
    collector = _collector()
    raw = {
        "tag_name": "v1.0.0",
        "name": "Version 1.0 GA",
        "body": "",
        "html_url": "https://github.com/org/repo/releases/tag/v1.0.0",
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.title == "Version 1.0 GA"


# ---------------------------------------------------------------------------
# AC-V2-003-008: null body → ""
# ---------------------------------------------------------------------------


def test_map_release_null_body_becomes_empty_string():
    """Null release body is coerced to empty string (AC-V2-003-008)."""
    collector = _collector()
    raw = {
        "tag_name": "v1.0.0",
        "name": "v1.0.0",
        "body": None,
        "html_url": "https://github.com/org/repo/releases/tag/v1.0.0",
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.body == ""


# ---------------------------------------------------------------------------
# AC-V2-003-009: null html_url → ""
# ---------------------------------------------------------------------------


def test_map_release_null_url_becomes_empty_string():
    """Null html_url is coerced to empty string (AC-V2-003-009)."""
    collector = _collector()
    raw = {
        "tag_name": "v1.0.0",
        "name": "v1.0.0",
        "body": "notes",
        "html_url": None,
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.url == ""


def test_map_release_missing_url_becomes_empty_string():
    """Missing html_url key gives empty string (AC-V2-003-009)."""
    collector = _collector()
    raw = {
        "tag_name": "v1.0.0",
        "name": "v1.0.0",
        "body": "notes",
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.url == ""


# ---------------------------------------------------------------------------
# AC-V2-003-010: created_at = published_at (raw ISO string, unchanged)
# ---------------------------------------------------------------------------


def test_map_release_created_at_is_published_at_unchanged():
    """created_at stores published_at as-is, never reformatted (AC-V2-003-010)."""
    collector = _collector()
    ts = "2026-07-01T09:00:00Z"
    raw = {
        "tag_name": "v1.0.0",
        "name": "v1.0.0",
        "body": "",
        "html_url": "https://github.com/org/repo/releases/tag/v1.0.0",
        "published_at": ts,
        "created_at": "2026-06-01T08:00:00Z",  # different — must NOT be used
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.created_at == ts  # published_at, not created_at of the release JSON


# ---------------------------------------------------------------------------
# AC-V2-003-011: skip when BOTH tag_name and id are missing
# ---------------------------------------------------------------------------


def test_map_release_returns_none_when_both_tag_name_and_id_missing():
    """Returns None when both tag_name and id are absent (AC-V2-003-011)."""
    collector = _collector()
    raw = {
        "name": "some name",
        "body": "notes",
        "html_url": "https://github.com/org/repo/releases/tag/v1.0.0",
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    assert collector._map_release(raw, REPO) is None


def test_map_release_uses_id_when_tag_name_missing():
    """Falls back to str(id) as item_id when tag_name is missing but id exists (AC-V2-003-011)."""
    collector = _collector()
    raw = {
        "id": 123456789,
        "name": "some release",
        "body": "",
        "html_url": "https://github.com/org/repo/releases/123456789",
        "published_at": "2026-07-01T09:00:00Z",
        "created_at": "2026-07-01T08:00:00Z",
    }
    item = collector._map_release(raw, REPO)
    assert item is not None
    assert item.item_id == "123456789"
