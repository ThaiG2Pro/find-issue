"""DiscordDelivery adapter — POST digest to a Discord webhook (AC-V2-005-001..011).

Implements ``osspulse.ports.Delivery`` Protocol structurally (no subclassing).
Only imports: stdlib + httpx + osspulse.delivery.errors (AC-V2-005-003).
No osspulse.github, summarizer, cache, or render imports.

Security: webhook URL is never included in DeliveryError messages or logs (T1,
AC-V2-005-011). Error text is composed from HTTP status codes and exception
*type names* only — never from str(exc) or repr(request), which embed the URL.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from osspulse.delivery.errors import DeliveryError

# ---------------------------------------------------------------------------
# Discord Embed helpers (AC-V4-001-001..008, AC-V4-002-009..011)
# ---------------------------------------------------------------------------

# Fixed item-type color map (AC-V4-002-010, ADR-003). No hash(), no PYTHONHASHSEED risk.
_ITEM_TYPE_COLORS: dict[str, int] = {
    "issue": 0xED4245,  # red
    "release": 0x57F287,  # green
    "discussion": 0x5865F2,  # Discord blurple
}
_ITEM_TYPE_COLOR_FALLBACK: int = 0x1ABC9C  # teal — for "other"/unknown types
_REPO_HEADER_COLOR: int = 0xFEE75C  # yellow — per-repo header embed (AC-V4-002-009)

# Discord hard limits for embed mode.
_EMBED_DESC_LIMIT = 4096  # code points per description (AC-V4-001-003)
_EMBED_BATCH_SIZE = 10  # max embeds per request (AC-V4-001-004)


def _parse_sections(content: str) -> list[dict]:
    """Split renderer output into per-repo sections with per-item data (AC-V4-001-001, ADR-003).

    Renderer emits:
    - ``## repo/name — N ngày qua`` section headers
    - ``### {label} (count)`` group headers within each section
    - ``- #{id} "{title}" — {summary} [link]({url})`` item lines

    Returns list of section dicts with keys:
    - ``title``: the ``## `` header text (``repo — N ngày qua``)
    - ``body``: raw body text (for legacy _build_embeds compatibility)
    - ``items``: list of parsed item dicts (repo, item_type, title, summary)

    Each item dict: ``{repo, item_type, title, summary}``.
    Returns ``[]`` when no ``## `` header is found (triggers plain-text fallback).
    """
    sections: list[dict] = []
    lines = content.splitlines(keepends=True)
    current_title: str | None = None
    current_body_lines: list[str] = []
    current_items: list[dict] = []
    current_item_type: str = "other"

    # Reverse map: renderer GROUP_LABELS -> item_type (ADR-003)
    _LABEL_TO_TYPE: dict[str, str] = {
        "Issue mới": "issue",
        "Discussion": "discussion",
        "Release": "release",
        "Khác": "other",
    }

    import re as _re

    # Tolerant item-line parser (ADR-003): - #{id} "{title}" — {summary} [link]({url})
    # All segments after the leading "- #id" are optional.
    _ITEM_RE = _re.compile(
        r"^- #\S+\s*"  # - #id (mandatory)
        r'(?:"(?P<title>[^"]*)")?\s*'  # optional "title"
        r"(?:\u2014\s*(?P<summary>.*?))?"  # optional — summary (em-dash U+2014)
        r"(?:\s*\[link\]\([^)]*\))?"  # optional [link](url)
        r"\s*$"
    )

    def _flush():
        if current_title is not None:
            sections.append(
                {
                    "title": current_title,
                    "body": "".join(current_body_lines).strip(),
                    "items": list(current_items),
                }
            )

    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("## "):
            _flush()
            current_title = stripped[3:]
            current_body_lines = [line]
            current_items = []
            current_item_type = "other"
        elif stripped.startswith("### "):
            current_body_lines.append(line)
            # Extract label between "### " and " (" to determine item_type
            label_part = stripped[4:]
            label = label_part.split(" (")[0].strip()
            current_item_type = _LABEL_TO_TYPE.get(label, "other")
        elif stripped.startswith("- #") and current_title is not None:
            current_body_lines.append(line)
            m = _ITEM_RE.match(stripped)
            if m:
                # Extract repo from current section title ("repo — N ngày qua")
                repo = current_title.split(" \u2014 ")[0].split(" —")[0].strip()
                current_items.append(
                    {
                        "repo": repo,
                        "item_type": current_item_type,
                        "title": (m.group("title") or "").strip(),
                        "summary": (m.group("summary") or "").strip(),
                    }
                )
        else:
            if current_title is not None:
                current_body_lines.append(line)

    _flush()
    return sections


def _split_description(body: str, limit: int = _EMBED_DESC_LIMIT) -> list[str]:
    """Split *body* into chunks ≤ *limit* code points by line (AC-V4-001-003)."""
    if len(body) <= limit:
        return [body]
    chunks: list[str] = []
    current = ""
    for line in body.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
        elif len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


def _build_embeds(sections: list[dict]) -> list[dict]:
    """Build Option-A Discord embed objects: header + per-item embeds (AC-V4-002-009..011).

    Per repo section:
    1. One header embed (color=_REPO_HEADER_COLOR, title=repo,
       description="{N} items — {lookback} ngày qua")
    2. One embed per parsed item (title truncated ≤256 code points, description=summary,
       color=_ITEM_TYPE_COLORS[item_type], footer="{repo} • {item_type} • OSS Pulse")

    Falls back to a plain body embed (legacy shape) when a section has zero parsed items,
    so the fallback path in deliver() can rely solely on total item count across sections.

    Existing _split_description / _batch_embeds / _post_one_embed are reused unchanged
    (AC-V4-001-003/004, T1).
    """
    ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    embeds: list[dict] = []

    for section in sections:
        title = section["title"]
        items = section.get("items", [])

        # Parse repo slug and lookback from "repo — N ngày qua"
        if " \u2014 " in title:
            repo_slug, rest = title.split(" \u2014 ", 1)
        elif " —" in title:
            repo_slug, rest = title.split(" —", 1)
            rest = rest.strip()
        else:
            repo_slug = title
            rest = ""

        # Extract lookback number from "N ngày qua"
        lookback_str = rest.strip()

        if items:
            # Header embed (AC-V4-002-009)
            n_shown = len(items)
            if lookback_str:
                header_desc = f"{n_shown} items — {lookback_str}"
            else:
                header_desc = f"{n_shown} items"
            embeds.append(
                {
                    "title": repo_slug,
                    "description": header_desc,
                    "color": _REPO_HEADER_COLOR,
                    "footer": {"text": f"OSS Pulse \u2022 {ts}"},
                }
            )
            # Per-item embeds (AC-V4-002-010/011)
            for item in items:
                item_type = item["item_type"]
                color = _ITEM_TYPE_COLORS.get(item_type, _ITEM_TYPE_COLOR_FALLBACK)
                item_title = item["title"][:256] if item["title"] else repo_slug
                summary = item["summary"] or "(no summary)"
                embeds.append(
                    {
                        "title": item_title,
                        "description": summary,
                        "color": color,
                        "footer": {"text": f"{repo_slug} \u2022 {item_type} \u2022 OSS Pulse"},
                    }
                )
        else:
            # Zero items parsed — emit a plain body embed (legacy shape, used by fallback check)
            body = section.get("body", "")
            color = _REPO_HEADER_COLOR
            desc_chunks = _split_description(body)
            for i, chunk in enumerate(desc_chunks):
                embed: dict = {
                    "title": title if i == 0 else f"{title} (cont.)",
                    "description": chunk,
                    "color": color,
                    "footer": {"text": f"OSS Pulse \u2022 {ts}"},
                }
                embeds.append(embed)

    return embeds


def _batch_embeds(embeds: list[dict], size: int = _EMBED_BATCH_SIZE) -> list[list[dict]]:
    """Batch embeds into groups of ≤ *size* (AC-V4-001-004)."""
    return [embeds[i : i + size] for i in range(0, len(embeds), size)]


# ---------------------------------------------------------------------------
# Discord hard limit per message (plain-text mode)
# ---------------------------------------------------------------------------

# Discord hard limit per message — counted in Unicode characters (code points),
# NOT bytes.  Python len(str) counts code points, which is correct here.
_DISCORD_CHAR_LIMIT = 2000


# ---------------------------------------------------------------------------
# Pure split helper (AC-V2-005-004..007, ADR-002)
# ---------------------------------------------------------------------------


def _split_for_discord(content: str, limit: int = _DISCORD_CHAR_LIMIT) -> list[str]:
    """Split *content* into messages each ≤ *limit* Unicode characters.

    Algorithm (ADR-002 two-level split):
    1. Split the content at ``## `` repo-section boundaries (renderer output).
    2. Greedily accumulate sections into a message while len(message) <= limit.
    3. A section that alone exceeds *limit* is further split by line.
    4. A single line that still exceeds *limit* is hard-sliced by character.

    All measurements use ``len(str)`` — Unicode code points (AC-V2-005-007).
    Never emits a message longer than *limit* characters.
    """
    if len(content) <= limit:
        return [content]

    # Split at every "## " that starts a line, keeping the delimiter with the
    # following text so each section begins with its "## repo …" header.
    raw_sections: list[str] = []
    current_start = 0
    for i, char in enumerate(content):
        if char == "#" and content[i : i + 3] == "## " and i > 0 and content[i - 1] == "\n":
            raw_sections.append(content[current_start:i])
            current_start = i
    raw_sections.append(content[current_start:])

    messages: list[str] = []
    current_msg = ""

    for section in raw_sections:
        if len(section) > limit:
            # This section alone is too large — flush pending message, then
            # split the section by line (level-2 fallback).
            if current_msg:
                messages.append(current_msg)
                current_msg = ""
            for line in _split_lines(section, limit):
                messages.append(line)
        elif len(current_msg) + len(section) <= limit:
            current_msg += section
        else:
            # Adding this section would overflow — flush and start fresh.
            if current_msg:
                messages.append(current_msg)
            current_msg = section

    if current_msg:
        messages.append(current_msg)

    # Safety-net: should be unreachable after the above logic, but guard anyway.
    return [m for chunk in messages for m in _enforce_limit(chunk, limit)]


def _split_lines(text: str, limit: int) -> list[str]:
    """Split *text* by newline; hard-slice any line that alone exceeds *limit*."""
    result: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            # Single line exceeds limit — hard character-slice.
            if current:
                result.append(current)
                current = ""
            for chunk in _char_slice(line, limit):
                result.append(chunk)
        elif len(current) + len(line) <= limit:
            current += line
        else:
            if current:
                result.append(current)
            current = line
    if current:
        result.append(current)
    return result


def _char_slice(text: str, limit: int) -> list[str]:
    """Hard-slice *text* into chunks of exactly *limit* characters."""
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _enforce_limit(text: str, limit: int) -> list[str]:
    """Safety-net: if *text* somehow exceeds *limit*, char-slice it."""
    if len(text) <= limit:
        return [text]
    return _char_slice(text, limit)


# ---------------------------------------------------------------------------
# DiscordDelivery adapter (AC-V2-005-001..011)
# ---------------------------------------------------------------------------


class DiscordDelivery:
    """Concrete Delivery adapter that POSTs the digest to a Discord webhook.

    Implements the ``osspulse.ports.Delivery`` Protocol structurally (no
    subclassing).  The webhook URL is accepted pre-validated from load_config
    (ADR-003) — this class does NOT re-read env vars.

    The *client* parameter exists solely for test injection (AC-V2-005-003).
    Production code passes ``client=None`` and a fresh httpx.Client is created
    internally and closed after the call.
    """

    def __init__(
        self,
        webhook_url: str,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
        use_embeds: bool = False,
    ) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout
        self._external_client = client  # None → create internally
        self._use_embeds = use_embeds

    def deliver(self, content: str) -> None:
        """Split *content* and POST each chunk to the Discord webhook (AC-V2-005-001).

        When ``use_embeds=True`` and the content contains ``## `` section headers,
        POST Discord Embed objects ({embeds: [...]}) instead of plain text
        (AC-V4-001-005/006).  Falls back to plain text when no sections are found.

        Failure semantics (BR-V2-005-004):
        - Any non-2xx response   → DeliveryError (AC-V2-005-008)
        - Connection/DNS error   → DeliveryError (AC-V2-005-009)
        - Timeout (~self._timeout s) → DeliveryError (AC-V2-005-010)
        - Multi-message: fail fatally at first failure; earlier messages already
          delivered (RISK-1, no rollback).

        Error messages are built from status codes / exception type names — the
        webhook URL is NEVER included (AC-V2-005-011).
        """
        if self._use_embeds:
            sections = _parse_sections(content)
            if sections:
                # ADR-003 fallback: if ALL sections yielded zero parsed items,
                # treat as format-drift and fall through to plain text (AC-V4-001-006)
                total_items = sum(len(s.get("items", [])) for s in sections)
                if total_items > 0:
                    embeds = _build_embeds(sections)
                    batches = _batch_embeds(embeds)
                    if self._external_client is not None:
                        self._post_embed_batches(self._external_client, batches)
                    else:
                        with httpx.Client(timeout=self._timeout) as client:
                            self._post_embed_batches(client, batches)
                    return
                # zero items parsed — fall through to plain-text path
            # No ## sections found or zero items parsed — fall through (AC-V4-001-006)

        messages = _split_for_discord(content)
        if self._external_client is not None:
            self._post_all(self._external_client, messages)
        else:
            with httpx.Client(timeout=self._timeout) as client:
                self._post_all(client, messages)

    def _post_all(self, client: httpx.Client, messages: list[str]) -> None:
        """POST each message sequentially; raise DeliveryError on any failure."""
        for i, msg in enumerate(messages, start=1):
            self._post_one(client, msg, index=i, total=len(messages))

    def _post_embed_batches(self, client: httpx.Client, batches: list[list[dict]]) -> None:
        """POST each embed batch sequentially (AC-V4-001-004/007)."""
        for i, batch in enumerate(batches, start=1):
            self._post_one_embed(client, batch, index=i, total=len(batches))

    def _post_one_embed(
        self, client: httpx.Client, embeds: list[dict], *, index: int, total: int
    ) -> None:
        """POST a single embed batch; raise DeliveryError without leaking the URL."""
        try:
            response = client.post(
                self._webhook_url,
                json={"embeds": embeds},
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise DeliveryError(
                f"discord embed delivery timed out after {self._timeout}s (batch {index}/{total})"
            ) from exc
        except httpx.RequestError as exc:
            raise DeliveryError(
                f"discord embed delivery failed: {type(exc).__name__} (batch {index}/{total})"
            ) from exc

        if not (200 <= response.status_code < 300):
            raise DeliveryError(
                f"discord embed delivery failed: HTTP {response.status_code}"
                f" (batch {index}/{total})"
            )

    def _post_one(self, client: httpx.Client, msg: str, *, index: int, total: int) -> None:
        """POST a single message; raise DeliveryError without leaking the URL."""
        try:
            response = client.post(
                self._webhook_url,
                json={"content": msg},
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            # Build message from exception type — NOT str(exc) which embeds URL.
            raise DeliveryError(
                f"discord delivery timed out after {self._timeout}s (message {index}/{total})"
            ) from exc
        except httpx.RequestError as exc:
            # RequestError covers ConnectError, DNS, etc.
            raise DeliveryError(
                f"discord delivery failed: {type(exc).__name__} (message {index}/{total})"
            ) from exc

        if not (200 <= response.status_code < 300):
            # Any 2xx (incl. 204) is success; anything else is fatal.
            raise DeliveryError(
                f"discord delivery failed: HTTP {response.status_code} (message {index}/{total})"
            )
