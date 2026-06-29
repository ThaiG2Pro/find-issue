"""Markdown digest renderer — implements ``osspulse.ports.DigestRenderer`` (AC-5-001..020).

Pure transform: render(items, *, lookback_days) -> str.  No file, network, LLM, or
state I/O.  Only imports: osspulse.models and stdlib.  No import of osspulse.github,
osspulse.state, osspulse.summarizer, or osspulse.cache (AC-5-003).

Security: no secrets, no PII, no I/O — pure in-memory transform (STRIDE not triggered).
"""

from osspulse.models import SummarizedItem

# ---------------------------------------------------------------------------
# Constants (AC-5-006, AC-5-014, BR-5-004, BR-5-008)
# ---------------------------------------------------------------------------

GROUP_ORDER: list[str] = ["issue", "discussion", "release"]

GROUP_LABELS: dict[str, str] = {
    "issue": "Issue mới",
    "discussion": "Discussion",
    "release": "Release",
    "__other__": "Khác",
}


# ---------------------------------------------------------------------------
# Module-private helper: line builder (Flow 3, AC-5-012, AC-5-015..018)
# ---------------------------------------------------------------------------


def _build_item_line(item: SummarizedItem) -> str:
    """Compose a single Markdown list line for *item*.

    Segments:
    - ``- #{item_id}``                always present
    - ``"{title}"``                   omitted when title is empty (AC-5-015)
    - ``— {summary}``                 omitted when summary is empty/whitespace (AC-5-017)
    - ``[link]({url})``               omitted when url is empty (AC-5-016)

    Segments are joined with single spaces so AC-5-012 byte-matches exactly.
    Never raises (AC-5-018); renders field text as-is — no Markdown escaping (A-A4).
    """
    raw = item.raw
    parts: list[str] = [f"- #{raw.item_id}"]

    if raw.title:  # AC-5-015: omit quoted title if empty
        parts.append(f'"{raw.title}"')

    if item.summary.strip():  # AC-5-017: omit if empty/whitespace
        parts.append(f"— {item.summary}")  # em-dash U+2014

    if raw.url:  # AC-5-016: omit link if url is empty
        parts.append(f"[link]({raw.url})")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Pure free function: the actual renderer logic (Flows 1 + 2)
# ---------------------------------------------------------------------------


def render(items: list[SummarizedItem], *, lookback_days: int) -> str:
    """Transform *items* into a Markdown digest string (AC-5-001..020).

    Deterministic (AC-5-004): output is a pure function of *items* + *lookback_days*.
    Repos sorted case-insensitively (AC-5-005, BR-5-003).  Groups in fixed order
    Issues → Discussions → Releases → Khác (AC-5-006, BR-5-004).  Items within a
    group in input order (AC-5-007).  NO set used anywhere (ADR-003, RF-1).

    Empty *items* returns a non-empty "No new items" doc; never returns "" (AC-5-008/009).
    """
    lines: list[str] = ["# OSS Pulse Digest"]

    # -- Empty input (Flow 2, AC-5-008/009, BR-5-005) -----------------------
    if not items:
        lines.append("")
        lines.append(f"No new items in the last {lookback_days} days")
        lines.append("")
        return "\n".join(lines)

    # -- Group into dict[repo] -> dict[group_key] -> list  (ADR-003) --------
    # Use plain dict (Python 3.13 guarantees insertion order) — NO set.
    grouped: dict[str, dict[str, list[SummarizedItem]]] = {}
    for item in items:
        repo = item.raw.repo
        item_type = item.raw.item_type
        group_key = item_type if item_type in GROUP_ORDER else "__other__"

        if repo not in grouped:
            grouped[repo] = {}
        if group_key not in grouped[repo]:
            grouped[repo][group_key] = []
        grouped[repo][group_key].append(item)

    # -- Emit repos in case-insensitive alphabetical order (AC-5-005) -------
    for repo in sorted(grouped, key=str.lower):  # sort ONLY repo keys
        lines.append("")
        lines.append(f"## {repo} — {lookback_days} ngày qua")  # AC-5-013

        repo_groups = grouped[repo]
        for gkey in GROUP_ORDER + ["__other__"]:
            group_items = repo_groups.get(gkey)
            if not group_items:  # AC-5-011: skip empty groups
                continue
            label = GROUP_LABELS[gkey]
            lines.append(f"### {label} ({len(group_items)})")  # AC-5-014
            for it in group_items:  # items in input order (AC-5-007)
                lines.append(_build_item_line(it))

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Adapter class: implements DigestRenderer Protocol structurally (ADR-001/002)
# ---------------------------------------------------------------------------


class MarkdownDigestRenderer:
    """Thin adapter implementing ``osspulse.ports.DigestRenderer`` structurally.

    Logic lives entirely in the module-level ``render()`` free function.
    This class provides the role-named port for S6/S7 wiring without duplicating
    any logic (ADR-001).  No I/O methods — delivery is S6 Delivery's job (AC-5-002).
    """

    def render(self, items: list[SummarizedItem], *, lookback_days: int) -> str:
        """Delegate to the pure free ``render()`` function (AC-5-001/002)."""
        return render(items, lookback_days=lookback_days)
