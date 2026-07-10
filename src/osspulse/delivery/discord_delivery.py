"""DiscordDelivery adapter — POST digest to a Discord webhook (AC-V2-005-001..011).

Implements ``osspulse.ports.Delivery`` Protocol structurally (no subclassing).
Only imports: stdlib + httpx + osspulse.delivery.errors (AC-V2-005-003).
No osspulse.github, summarizer, cache, or render imports.

Security: webhook URL is never included in DeliveryError messages or logs (T1,
AC-V2-005-011). Error text is composed from HTTP status codes and exception
*type names* only — never from str(exc) or repr(request), which embed the URL.
"""

from __future__ import annotations

import httpx

from osspulse.delivery.errors import DeliveryError

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
    ) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout
        self._external_client = client  # None → create internally

    def deliver(self, content: str) -> None:
        """Split *content* and POST each chunk to the Discord webhook (AC-V2-005-001).

        Failure semantics (BR-V2-005-004):
        - Any non-2xx response   → DeliveryError (AC-V2-005-008)
        - Connection/DNS error   → DeliveryError (AC-V2-005-009)
        - Timeout (~self._timeout s) → DeliveryError (AC-V2-005-010)
        - Multi-message: fail fatally at first failure; earlier messages already
          delivered (RISK-1, no rollback).

        Error messages are built from status codes / exception type names — the
        webhook URL is NEVER included (AC-V2-005-011).
        """
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
