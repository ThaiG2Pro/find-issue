"""DiscordDelivery adapter — POST digest to a Discord webhook (AC-V2-005-001..011).

Implements ``osspulse.ports.Delivery`` Protocol structurally (no subclassing).
Only imports: stdlib + httpx + osspulse.delivery.errors (AC-V2-005-003).
No osspulse.github, summarizer, cache, or render imports.

Security: webhook URL is never included in DeliveryError messages or logs (T1,
AC-V2-005-011). Error text is composed from HTTP status codes and exception
*type names* only — never from str(exc) or repr(request), which embed the URL.
"""

from __future__ import annotations

import time
from collections.abc import Callable
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
        r'(?:"(?P<title>[^"]*)")? \s*'  # optional "title"
        r"(?:\u2014\s*(?P<summary>.*?))?"  # optional — summary (em-dash U+2014)
        r"(?:\s*\[link\]\((?P<url>[^)]*)\))?"  # optional [link](url) — capture url
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
                        "url": (m.group("url") or "").strip(),
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
                embed = {
                    "title": item_title,
                    "description": summary,
                    "color": color,
                    "footer": {"text": f"{repo_slug} \u2022 {item_type} \u2022 OSS Pulse"},
                }
                if item.get("url"):
                    embed["url"] = item["url"]
                embeds.append(embed)
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
# DiscordDelivery adapter (AC-V2-005-001..011, AC-001-001..011)
# ---------------------------------------------------------------------------


class DiscordDelivery:
    """Concrete Delivery adapter that POSTs the digest to a Discord webhook.

    Implements the ``osspulse.ports.Delivery`` Protocol structurally (no
    subclassing).  The webhook URL is accepted pre-validated from load_config
    (ADR-003) — this class does NOT re-read env vars.

    The *client* parameter exists solely for test injection (AC-V2-005-003).
    Production code passes ``client=None`` and a fresh httpx.Client is created
    internally and closed after the call.

    Retry params (AC-001-001..011):
    - *max_retries*: max retries after the initial attempt (default 3; 0 = no retry).
    - *backoff_base*: base seconds for exponential backoff ``backoff_base * 2**attempt``
      (default 1.0).
    - *sleep*: callable invoked between retry attempts (default ``time.sleep``; inject
      a fake in tests to avoid real delays).
    """

    def __init__(
        self,
        webhook_url: str,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
        use_embeds: bool = False,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout
        self._external_client = client  # None → create internally
        self._use_embeds = use_embeds
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep

    def deliver(self, content: str) -> None:
        """Split *content* and POST each chunk to the Discord webhook (AC-V2-005-001).

        When ``use_embeds=True`` and the content contains ``## `` section headers,
        POST Discord Embed objects ({embeds: [...]}) instead of plain text
        (AC-V4-001-005/006).  Falls back to plain text when no sections are found.

        Failure semantics (BR-V2-005-004, AC-001-001..011):
        - Transient failures (429/5xx/TimeoutException/RequestError) are retried up to
          max_retries times with exponential backoff, Retry-After-floored for 429.
        - Non-transient 4xx (except 429) → DeliveryError immediately, no sleep.
        - After budget exhausted → DeliveryError; error built from status/type-name only.
        - Multi-message: per-POST retry budget; already-delivered POSTs never re-sent.

        Error messages are built from status codes / exception type names — the
        webhook URL is NEVER included (AC-V2-005-011, AC-001-010).
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

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        """Return the Retry-After header as a finite float, or None if missing/non-numeric.

        Never raises — treats any malformed value as absent (AC-001-006, BR-001-003).
        """
        raw = response.headers.get("Retry-After", "")
        if not raw:
            return None
        try:
            value = float(raw)
        except (ValueError, OverflowError):
            return None
        import math

        if not math.isfinite(value):
            return None
        return value

    def _do_post_with_retry(
        self,
        client: httpx.Client,
        *,
        json_body: dict,
        noun: str,
        unit: str,
        index: int,
        total: int,
    ) -> None:
        """Shared per-POST attempt loop with retry + backoff (AC-001-001..011, ADR-001).

        Classifies each failure as transient (429/5xx/TimeoutException/RequestError) or
        non-transient (other non-2xx 4xx).  Transient failures are retried up to
        self._max_retries times; non-transient failures raise immediately.

        Backoff wait = max(Retry-After, backoff_base * 2**attempt) when a numeric
        Retry-After header is present; pure backoff otherwise (ADR-002).

        sleep() is called only between attempts, never after the final failure
        (AC-001-002, AC-001-003).  Error text is built from status code or exception
        type name only — never str(exc) or repr(request) (T1, AC-001-010).
        """
        attempt = 0
        while True:
            # --- attempt ---
            transient = False
            retry_after: float | None = None
            error_msg: str | None = None

            try:
                response = client.post(
                    self._webhook_url,
                    json=json_body,
                    timeout=self._timeout,
                )
            except httpx.TimeoutException:
                # TimeoutException must be caught before RequestError (subclass ordering)
                transient = True
                error_msg = f"{noun} timed out after {self._timeout}s ({unit} {index}/{total})"
            except httpx.RequestError as exc:
                transient = True
                error_msg = f"{noun} failed: {type(exc).__name__} ({unit} {index}/{total})"
            else:
                if 200 <= response.status_code < 300:
                    return  # success
                status = response.status_code
                transient = status == 429 or 500 <= status <= 599
                retry_after = self._parse_retry_after(response) if transient else None
                error_msg = f"{noun} failed: HTTP {status} ({unit} {index}/{total})"

            # --- retry or raise ---
            if transient and attempt < self._max_retries:
                backoff = self._backoff_base * (2**attempt)
                wait = max(retry_after, backoff) if retry_after is not None else backoff
                self._sleep(wait)
                attempt += 1
                continue

            raise DeliveryError(error_msg)  # type: ignore[arg-type]

    def _post_one_embed(
        self, client: httpx.Client, embeds: list[dict], *, index: int, total: int
    ) -> None:
        """POST a single embed batch via the shared retry helper (AC-001-008, ADR-001)."""
        self._do_post_with_retry(
            client,
            json_body={"embeds": embeds},
            noun="discord embed delivery",
            unit="batch",
            index=index,
            total=total,
        )

    def _post_one(self, client: httpx.Client, msg: str, *, index: int, total: int) -> None:
        """POST a single message via the shared retry helper (AC-001-001..011, ADR-001)."""
        self._do_post_with_retry(
            client,
            json_body={"content": msg},
            noun="discord delivery",
            unit="message",
            index=index,
            total=total,
        )
