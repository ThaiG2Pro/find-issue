"""Cache-key helpers — pure functions, no I/O (AC-4-006, AC-4-007, ADR-003).

``content_hash`` is computed over the TRUNCATED text that is actually sent to the LLM
so the cache key stays stable across runs (AC-4-019).
"""

import hashlib

from osspulse.models import RawItem


def content_hash(title: str, body: str) -> str:
    """Return SHA-256 hex of ``title + "\\n" + body`` (AC-4-007, ADR-003).

    The newline separator prevents concatenation collisions (e.g. ``("ab","c")`` vs
    ``("a","bc")``).  Both inputs must already be the truncated strings that are sent
    to the LLM so the key is stable across runs (AC-4-019).
    """
    text = title + "\n" + body
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key(item: RawItem, hash_: str) -> str:
    """Return ``summary:{repo}:{item_type}:{item_id}:{content_hash}`` (AC-4-006)."""
    return f"summary:{item.repo}:{item.item_type}:{item.item_id}:{hash_}"
