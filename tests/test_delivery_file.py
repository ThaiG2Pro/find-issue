"""Unit tests for FileDelivery (AC-6-004..006, AC-6-014..020)."""

import os
from unittest.mock import patch

import pytest

from osspulse.delivery.errors import DeliveryError
from osspulse.delivery.file_delivery import FileDelivery

# ---------------------------------------------------------------------------
# Happy path — Task 8.1
# ---------------------------------------------------------------------------


def test_file_delivery_utf8_roundtrip(tmp_path):
    """Successful delivery writes exact content as UTF-8 including non-ASCII (AC-6-004)."""
    content = "# Khác\n## Summary\nhello 🎉"
    out = tmp_path / "digest.md"
    FileDelivery(str(out)).deliver(content)
    assert out.read_text(encoding="utf-8") == content


def test_file_delivery_atomic_temp_then_replace(tmp_path):
    """Temp file is in same directory and target is replaced atomically (AC-6-005)."""
    out = tmp_path / "digest.md"
    temps_before = set(tmp_path.iterdir())
    FileDelivery(str(out)).deliver("content")
    temps_after = set(tmp_path.iterdir())
    assert out in temps_after
    # no stray temp file left behind
    assert temps_after - temps_before == {out}


def test_file_delivery_idempotent_overwrite(tmp_path):
    """Re-delivering same content overwrites byte-identically, never appends (AC-6-018)."""
    out = tmp_path / "digest.md"
    content = "# digest"
    FileDelivery(str(out)).deliver(content)
    size_after_first = out.stat().st_size
    FileDelivery(str(out)).deliver(content)
    assert out.read_text(encoding="utf-8") == content
    assert out.stat().st_size == size_after_first


def test_file_delivery_different_content_replaces(tmp_path):
    """Different content fully replaces previous content, no append (AC-6-019)."""
    out = tmp_path / "digest.md"
    FileDelivery(str(out)).deliver("old content")
    FileDelivery(str(out)).deliver("new content")
    assert out.read_text(encoding="utf-8") == "new content"


def test_file_delivery_no_new_items_verbatim(tmp_path):
    """'No new items' doc is delivered verbatim, not suppressed (AC-6-020)."""
    content = "# OSS Pulse Digest\n\nNo new items in the last 7 days."
    out = tmp_path / "digest.md"
    FileDelivery(str(out)).deliver(content)
    assert out.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# Failure modes — Task 8.2
# ---------------------------------------------------------------------------


def test_missing_parent_raises_delivery_error(tmp_path):
    """Missing parent directory raises DeliveryError naming the path (AC-6-014, AC-6-015)."""
    out = tmp_path / "nope" / "digest.md"
    with pytest.raises(DeliveryError) as exc_info:
        FileDelivery(str(out)).deliver("content")
    assert "digest.md" in str(exc_info.value) or "nope" in str(exc_info.value)


def test_permission_denied_raises_delivery_error(tmp_path):
    """Permission denied on target dir raises DeliveryError (AC-6-016)."""
    out = tmp_path / "digest.md"
    os.chmod(tmp_path, 0o444)
    try:
        with pytest.raises(DeliveryError):
            FileDelivery(str(out)).deliver("content")
    finally:
        os.chmod(tmp_path, 0o755)


def test_target_is_directory_raises_delivery_error(tmp_path):
    """Target path that is an existing directory raises DeliveryError (AC-6-017)."""
    target_dir = tmp_path / "digest.md"
    target_dir.mkdir()
    with pytest.raises(DeliveryError):
        FileDelivery(str(target_dir)).deliver("content")


def test_failed_replace_leaves_original_intact(tmp_path):
    """Failed os.replace leaves existing target intact and cleans up temp (AC-6-006)."""
    out = tmp_path / "digest.md"
    out.write_text("original", encoding="utf-8")
    with patch("osspulse.delivery.file_delivery.os.replace", side_effect=OSError("replace failed")):
        with pytest.raises(DeliveryError):
            FileDelivery(str(out)).deliver("new content")
    # original file is untouched
    assert out.read_text(encoding="utf-8") == "original"
    # no temp file left behind
    leftover = [p for p in tmp_path.iterdir() if p != out]
    assert leftover == [], f"stray temp files: {leftover}"


def test_no_mkdir_on_missing_parent(tmp_path):
    """Delivery does NOT create missing parent directory (AC-6-014)."""
    out = tmp_path / "subdir" / "digest.md"
    with pytest.raises(DeliveryError):
        FileDelivery(str(out)).deliver("content")
    assert not (tmp_path / "subdir").exists()
