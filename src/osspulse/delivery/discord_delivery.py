"""DiscordDelivery adapter — POST digest to a Discord webhook (AC-V2-005-001..011).

Implements ``osspulse.ports.Delivery`` Protocol structurally (no subclassing).
Only imports: stdlib + httpx + osspulse.delivery.errors (AC-V2-005-003).
No osspulse.github, summarizer, cache, or render imports.

Security: webhook URL is never included in DeliveryError messages or logs (T1,
AC-V2-005-011). Error text is composed from HTTP status codes and exception
*type names* only — never from str(exc) or repr(request), which embed the URL.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import httpx

from osspulse.delivery.errors import DeliveryError

# ---------------------------------------------------------------------------
# Discord Embed helpers (AC-V4-001-001..008)
# ---------------------------------------------------------------------------

# Fixed palette of 6 visually distinct Discord-safe colours (ADR-002).
# Index derived via hashlib — never builtin hash() (PYTHONHASHSEED-salted).
_EMBED_PALETTE: list[int] = [
    0x5865F2,  # Discord blurple
    0x57F287,  # green
    0xFEE75C,  # yellow
    0xED4245,  # red
    0xEB459E,  # pink
    0x1ABC9C,  # teal
]

# Discord hard limits for embed mode.
_EMBED_DESC_LIMIT = 4096  # code points per description (AC-V4-001-003)
_EMBED_BATCH_SIZE = 10  # max embeds per request (AC-V4-001-004)


def _color_for_repo(slug: str) -> int:
    """Return a deterministic palette colour for *slug* (AC-V4-001-002, ADR-002).

    Uses hashlib.md5 — stable across Python versions and PYTHONHASHSEED values.
    Never uses builtin hash() which is salted per-process.
    """
    digest = hashlib.md5(slug.encode(), usedforsecurity=False).digest()
    return _EMBED_PALETTE[digest[0] % len(_EMBED_PALETTE)]


def _parse_sections(content: str) -> list[dict[str, str]]:
    """Split renderer output into per-repo sections (AC-V4-001-001).

    Renderer emits ``## repo/name — N ngày qua`` as section headers.
    Returns list of ``{title, body}`` dicts.  Returns ``[]`` when no ``## ``
    header is found (triggers plain-text fallback in deliver()).
    """
    sections: list[dict[str, str]] = []
    lines = content.splitlines(keepends=True)
    current_title: str | None = None
    current_body_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_title is not None:
                sections.append(
                    {
                        "title": current_title,
                        "body": "".join(current_body_lines).strip(),
                    }
                )
            current_title = line[3:].rstrip("\n")
            current_body_lines = []
        else:
            current_body_lines.append(line)

    if current_title is not None:
        sections.append({"title": current_title, "body": "".join(current_body_lines).strip()})

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


def _build_embeds(sections: list[dict[str, str]]) -> list[dict]:
    """Build Discord embed objects from parsed sections (AC-V4-001-001..004)."""
    ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    embeds: list[dict] = []
    for section in sections:
        title = section["title"]
        body = section["body"]
        repo_slug = title.split(" —")[0].strip() if " —" in title else title
        color = _color_for_repo(repo_slug)
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
                embeds = _build_embeds(sections)
                batches = _batch_embeds(embeds)
                if self._external_client is not None:
                    self._post_embed_batches(self._external_client, batches)
                else:
                    with httpx.Client(timeout=self._timeout) as client:
                        self._post_embed_batches(client, batches)
                return
            # No ## sections found — fall through to plain-text path (AC-V4-001-006)

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
