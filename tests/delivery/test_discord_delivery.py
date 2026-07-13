"""Unit tests for DiscordDelivery adapter (AC-V2-005-001..003, 008..011)."""

import hashlib as _hashlib
import sys
from unittest.mock import MagicMock

import httpx
import pytest

from osspulse.delivery.discord_delivery import (
    _EMBED_PALETTE,
    DiscordDelivery,
    _batch_embeds,
    _build_embeds,
    _color_for_repo,
    _parse_sections,
    _split_description,
)
from osspulse.delivery.errors import DeliveryError

WEBHOOK_URL = "https://discord.com/api/webhooks/123/secret_token"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status_code: int) -> httpx.Response:
    """Build a minimal httpx.Response with the given status code."""
    return httpx.Response(status_code, request=httpx.Request("POST", WEBHOOK_URL))


def _mock_client(status_code: int = 204) -> MagicMock:
    """Return a mock httpx.Client whose .post() returns *status_code*."""
    client = MagicMock(spec=httpx.Client)
    client.post.return_value = _make_response(status_code)
    return client


# ---------------------------------------------------------------------------
# AC-V2-005-001 — single POST for short content
# ---------------------------------------------------------------------------


def test_short_content_sends_one_post(AC="AC-V2-005-001"):
    """Content ≤ 2000 chars → exactly one POST with {'content': text} (AC-V2-005-001)."""
    client = _mock_client(204)
    d = DiscordDelivery(WEBHOOK_URL, client=client)
    text = "# OSS Pulse Digest\n\nNo new items in the last 7 days\n"

    d.deliver(text)

    client.post.assert_called_once_with(
        WEBHOOK_URL,
        json={"content": text},
        timeout=10.0,
    )


def test_multi_message_sends_multiple_posts(AC="AC-V2-005-001"):
    """Digest > 2000 chars → one POST per split message (AC-V2-005-001)."""
    client = _mock_client(200)
    d = DiscordDelivery(WEBHOOK_URL, client=client)
    # Build content that will split into ≥2 messages
    section = "## owner/repo — 7 ngày qua\n" + ("- #1 item\n" * 80)
    content = "# OSS Pulse Digest\n\n" + section + section + section

    d.deliver(content)

    assert client.post.call_count >= 2
    for call in client.post.call_args_list:
        _, kwargs = call
        assert "content" in kwargs["json"]
        assert len(kwargs["json"]["content"]) <= 2000


def test_post_payload_structure(AC="AC-V2-005-001"):
    """POST body is JSON {'content': <str>} (AC-V2-005-001)."""
    client = _mock_client(204)
    d = DiscordDelivery(WEBHOOK_URL, client=client)
    d.deliver("hello world")

    _, kwargs = client.post.call_args
    assert kwargs["json"] == {"content": "hello world"}


# ---------------------------------------------------------------------------
# AC-V2-005-002 — structural port compatibility
# ---------------------------------------------------------------------------


def test_port_compatibility(AC="AC-V2-005-002"):
    """DiscordDelivery structurally satisfies the Delivery Protocol (AC-V2-005-002)."""
    # Delivery Protocol requires deliver(self, content: str) -> None
    # Verify by duck-type inspection (Protocol is not runtime_checkable)
    d = DiscordDelivery(WEBHOOK_URL, client=_mock_client())
    assert callable(getattr(d, "deliver", None)), "DiscordDelivery must have a deliver method"


def test_deliver_method_signature(AC="AC-V2-005-002"):
    """DiscordDelivery.deliver accepts a single str and returns None (AC-V2-005-002)."""
    client = _mock_client(204)
    d = DiscordDelivery(WEBHOOK_URL, client=client)
    result = d.deliver("test content")
    assert result is None


# ---------------------------------------------------------------------------
# AC-V2-005-008 — non-2xx HTTP response → DeliveryError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503])
def test_non_2xx_raises_delivery_error(status, AC="AC-V2-005-008"):
    """Non-2xx HTTP status → DeliveryError (AC-V2-005-008)."""
    client = _mock_client(status)
    d = DiscordDelivery(WEBHOOK_URL, client=client)

    with pytest.raises(DeliveryError) as exc_info:
        d.deliver("content")

    assert str(status) in str(exc_info.value)


def test_2xx_204_is_success(AC="AC-V2-005-008"):
    """HTTP 204 (Discord typical response) is treated as success (AC-V2-005-008)."""
    client = _mock_client(204)
    d = DiscordDelivery(WEBHOOK_URL, client=client)
    d.deliver("content")  # must not raise


def test_2xx_200_is_success(AC="AC-V2-005-008"):
    """HTTP 200 is treated as success (AC-V2-005-008)."""
    client = _mock_client(200)
    d = DiscordDelivery(WEBHOOK_URL, client=client)
    d.deliver("content")  # must not raise


# ---------------------------------------------------------------------------
# AC-V2-005-009 — connection / DNS error → DeliveryError
# ---------------------------------------------------------------------------


def test_connect_error_raises_delivery_error(AC="AC-V2-005-009"):
    """httpx.ConnectError → DeliveryError (AC-V2-005-009)."""
    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = httpx.ConnectError("connection refused")
    d = DiscordDelivery(WEBHOOK_URL, client=client)

    with pytest.raises(DeliveryError, match="ConnectError"):
        d.deliver("content")


def test_network_error_raises_delivery_error(AC="AC-V2-005-009"):
    """httpx.NetworkError → DeliveryError (AC-V2-005-009)."""
    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = httpx.NetworkError("network failure")
    d = DiscordDelivery(WEBHOOK_URL, client=client)

    with pytest.raises(DeliveryError, match="NetworkError"):
        d.deliver("content")


# ---------------------------------------------------------------------------
# AC-V2-005-010 — timeout → DeliveryError
# ---------------------------------------------------------------------------


def test_timeout_raises_delivery_error(AC="AC-V2-005-010"):
    """httpx.TimeoutException → DeliveryError mentioning timeout (AC-V2-005-010)."""
    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = httpx.TimeoutException("timed out")
    d = DiscordDelivery(WEBHOOK_URL, timeout=10.0, client=client)

    with pytest.raises(DeliveryError, match="timed out"):
        d.deliver("content")


def test_read_timeout_raises_delivery_error(AC="AC-V2-005-010"):
    """httpx.ReadTimeout → DeliveryError (AC-V2-005-010)."""
    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = httpx.ReadTimeout("read timeout")
    d = DiscordDelivery(WEBHOOK_URL, client=client)

    with pytest.raises(DeliveryError):
        d.deliver("content")


# ---------------------------------------------------------------------------
# AC-V2-005-011 — webhook URL NEVER in error message
# ---------------------------------------------------------------------------


def test_http_error_does_not_leak_url(AC="AC-V2-005-011"):
    """DeliveryError from non-2xx must NOT contain the webhook URL (AC-V2-005-011)."""
    client = _mock_client(500)
    d = DiscordDelivery(WEBHOOK_URL, client=client)

    with pytest.raises(DeliveryError) as exc_info:
        d.deliver("content")

    error_msg = str(exc_info.value)
    assert WEBHOOK_URL not in error_msg
    assert "secret_token" not in error_msg


def test_connection_error_does_not_leak_url(AC="AC-V2-005-011"):
    """DeliveryError from connection error must NOT contain the webhook URL (AC-V2-005-011)."""
    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = httpx.ConnectError("connection refused")
    d = DiscordDelivery(WEBHOOK_URL, client=client)

    with pytest.raises(DeliveryError) as exc_info:
        d.deliver("content")

    error_msg = str(exc_info.value)
    assert WEBHOOK_URL not in error_msg
    assert "secret_token" not in error_msg


def test_timeout_error_does_not_leak_url(AC="AC-V2-005-011"):
    """DeliveryError from timeout must NOT contain the webhook URL (AC-V2-005-011)."""
    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = httpx.TimeoutException("timed out")
    d = DiscordDelivery(WEBHOOK_URL, client=client)

    with pytest.raises(DeliveryError) as exc_info:
        d.deliver("content")

    error_msg = str(exc_info.value)
    assert WEBHOOK_URL not in error_msg
    assert "secret_token" not in error_msg


def test_multi_message_second_fails_after_first_sent(AC="AC-V2-005-011"):
    """Multi-message: msg 2 fails → DeliveryError; msg 1 already POSTed (AC-V2-005-008/011)."""
    client = MagicMock(spec=httpx.Client)
    client.post.side_effect = [
        _make_response(204),  # msg 1: success
        httpx.ConnectError("fail"),  # msg 2: failure
    ]
    d = DiscordDelivery(WEBHOOK_URL, client=client)

    section = "## owner/repo — 7 ngày qua\n" + ("- #1 item\n" * 80)
    content = "# OSS Pulse Digest\n\n" + section + section + section

    with pytest.raises(DeliveryError) as exc_info:
        d.deliver(content)

    # msg 1 was posted
    assert client.post.call_count == 2
    # URL not in error
    assert WEBHOOK_URL not in str(exc_info.value)


# ---------------------------------------------------------------------------
# AC-V2-005-003 — no upstream imports
# ---------------------------------------------------------------------------


def test_no_upstream_imports(AC="AC-V2-005-003"):
    """discord_delivery module must not import github/summarizer/cache/render (AC-V2-005-003)."""
    import osspulse.delivery.discord_delivery as mod

    forbidden = {"osspulse.github", "osspulse.summarizer", "osspulse.cache", "osspulse.render"}
    # Inspect the module's globals for any imported module from the forbidden set.
    for name, obj in vars(mod).items():
        if hasattr(obj, "__module__"):
            for forbidden_prefix in forbidden:
                assert not (obj.__module__ or "").startswith(forbidden_prefix), (
                    f"{name} imports from forbidden module {obj.__module__}"
                )

    # Also check sys.modules for any import side-effects.
    for mod_name in sys.modules:
        for forbidden_prefix in forbidden:
            if mod_name.startswith(forbidden_prefix):
                # Only fail if that module was imported BY discord_delivery, not
                # already present from other test imports.
                source = getattr(sys.modules.get(mod_name), "__file__", "") or ""
                assert "discord_delivery" not in source, (
                    f"discord_delivery imported forbidden module {mod_name}"
                )


# ---------------------------------------------------------------------------
# V4-001 Discord Embed tests
# ---------------------------------------------------------------------------

_SAMPLE_CONTENT = """\
## vercel/next.js — 1 ngày qua
Some issue text here.
Another line.

## getlago/lago — 1 ngày qua
Release notes here.
"""

_NO_HEADER_CONTENT = "No new items in the last 1 days."


class TestParseSections:
    def test_splits_at_headers(self):
        """_parse_sections splits at ## boundaries (AC-V4-001-001)."""
        sections = _parse_sections(_SAMPLE_CONTENT)
        assert len(sections) == 2
        assert sections[0]["title"] == "vercel/next.js — 1 ngày qua"
        assert sections[1]["title"] == "getlago/lago — 1 ngày qua"
        assert "Some issue text" in sections[0]["body"]
        assert "Release notes" in sections[1]["body"]

    def test_no_headers_returns_empty(self):
        """_parse_sections returns [] when no ## headers present (AC-V4-001-002)."""
        assert _parse_sections(_NO_HEADER_CONTENT) == []

    def test_single_section(self):
        """Single section with no trailing ## (AC-V4-001-001)."""
        content = "## owner/repo — 1 ngày qua\nBody text."
        sections = _parse_sections(content)
        assert len(sections) == 1
        assert sections[0]["title"] == "owner/repo — 1 ngày qua"

    def test_empty_string_returns_empty(self):
        """Empty content returns empty list (AC-V4-001-002)."""
        assert _parse_sections("") == []


class TestColorForRepo:
    def test_deterministic_same_input(self):
        """Same slug always yields same color (AC-V4-001-002)."""
        c1 = _color_for_repo("vercel/next.js")
        c2 = _color_for_repo("vercel/next.js")
        assert c1 == c2

    def test_result_in_palette(self):
        """Color is always a member of the palette (AC-V4-001-002)."""
        for slug in ["vercel/next.js", "getlago/lago", "owner/repo", "a/b"]:
            assert _color_for_repo(slug) in _EMBED_PALETTE

    def test_uses_hashlib_not_builtin(self):
        """Color matches hashlib.md5 computation — not builtin hash() (AC-V4-001-002)."""
        slug = "vercel/next.js"
        expected_idx = _hashlib.md5(slug.encode(), usedforsecurity=False).digest()[0] % len(
            _EMBED_PALETTE
        )
        assert _color_for_repo(slug) == _EMBED_PALETTE[expected_idx]

    def test_different_slugs_can_differ(self):
        """Different slugs are not all the same color (palette diversity check)."""
        colors = {_color_for_repo(f"owner/repo{i}") for i in range(12)}
        assert len(colors) > 1


class TestSplitDescription:
    def test_short_body_unchanged(self):
        """Body ≤4096 chars returned as single chunk (AC-V4-001-003)."""
        body = "x" * 100
        assert _split_description(body) == [body]

    def test_long_body_split(self):
        """Body >4096 chars split into ≤4096-char chunks (AC-V4-001-003)."""
        body = ("A" * 80 + "\n") * 60  # ~4860 chars
        chunks = _split_description(body)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 4096

    def test_uses_code_points_not_bytes(self):
        """Measurement uses len() (code points), not byte length (AC-V4-001-003)."""
        # Vietnamese character = 3 bytes but 1 code point
        body = "à" * 4096
        chunks = _split_description(body)
        assert len(chunks) == 1  # exactly 4096 code points, fits


class TestBuildEmbeds:
    def test_one_embed_per_section(self):
        """Each section produces at least one embed (AC-V4-001-001)."""
        sections = _parse_sections(_SAMPLE_CONTENT)
        embeds = _build_embeds(sections)
        assert len(embeds) >= 2

    def test_embed_has_required_keys(self):
        """Each embed has title, description, color, footer (AC-V4-001-001)."""
        sections = [{"title": "vercel/next.js — 1 ngày qua", "body": "Some text."}]
        embed = _build_embeds(sections)[0]
        assert "title" in embed
        assert "description" in embed
        assert "color" in embed
        assert "footer" in embed
        assert "text" in embed["footer"]

    def test_footer_contains_oss_pulse(self):
        """Footer text contains 'OSS Pulse' (AC-V4-001-001)."""
        sections = [{"title": "owner/repo — 1 ngày qua", "body": "Body."}]
        embed = _build_embeds(sections)[0]
        assert "OSS Pulse" in embed["footer"]["text"]

    def test_description_truncated_at_4096(self):
        """Long body is split; each embed description ≤4096 code points (AC-V4-001-003)."""
        long_body = ("word " * 1000).strip()  # ~5000 chars
        sections = [{"title": "owner/repo — 1 ngày qua", "body": long_body}]
        embeds = _build_embeds(sections)
        for embed in embeds:
            assert len(embed["description"]) <= 4096


class TestBatchEmbeds:
    def test_batches_of_10(self):
        """11 embeds → 2 batches, first ≤10 (AC-V4-001-004)."""
        embeds = [{"title": str(i)} for i in range(11)]
        batches = _batch_embeds(embeds)
        assert len(batches) == 2
        assert len(batches[0]) == 10
        assert len(batches[1]) == 1

    def test_exactly_10_is_one_batch(self):
        """Exactly 10 embeds → 1 batch (AC-V4-001-004)."""
        embeds = [{"title": str(i)} for i in range(10)]
        assert len(_batch_embeds(embeds)) == 1

    def test_empty_returns_empty(self):
        assert _batch_embeds([]) == []


class TestDiscordDeliveryEmbedMode:
    def test_embed_mode_posts_embeds_json(self):
        """use_embeds=True + ## sections → POST {embeds: [...]} (AC-V4-001-005)."""
        client = _mock_client(204)
        delivery = DiscordDelivery(WEBHOOK_URL, client=client, use_embeds=True)
        delivery.deliver(_SAMPLE_CONTENT)
        call_kwargs = client.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "embeds" in body
        assert isinstance(body["embeds"], list)
        assert len(body["embeds"]) >= 1

    def test_plain_fallback_no_sections(self):
        """use_embeds=True but no ## headers → plain text {content:...} (AC-V4-001-006)."""
        client = _mock_client(204)
        delivery = DiscordDelivery(WEBHOOK_URL, client=client, use_embeds=True)
        delivery.deliver(_NO_HEADER_CONTENT)
        body = client.post.call_args.kwargs.get("json") or client.post.call_args[1]["json"]
        assert "content" in body
        assert "embeds" not in body

    def test_use_embeds_false_by_default(self):
        """Default use_embeds=False → always plain text (AC-V4-001-008)."""
        client = _mock_client(204)
        delivery = DiscordDelivery(WEBHOOK_URL, client=client)
        delivery.deliver(_SAMPLE_CONTENT)
        body = client.post.call_args.kwargs.get("json") or client.post.call_args[1]["json"]
        assert "content" in body

    def test_embed_post_non_2xx_raises_delivery_error(self):
        """Non-2xx embed response → DeliveryError without URL (AC-V4-001-007)."""
        client = _mock_client(400)
        delivery = DiscordDelivery(WEBHOOK_URL, client=client, use_embeds=True)
        with pytest.raises(DeliveryError) as exc_info:
            delivery.deliver(_SAMPLE_CONTENT)
        assert "secret_token" not in str(exc_info.value)
        assert "400" in str(exc_info.value)

    def test_embed_batching_sends_multiple_requests(self):
        """11 sections → 2 requests (≤10 embeds each) (AC-V4-001-004)."""
        client = _mock_client(204)
        content = "".join(f"## owner/repo{i} — 1 ngày qua\nBody {i}.\n" for i in range(11))
        delivery = DiscordDelivery(WEBHOOK_URL, client=client, use_embeds=True)
        delivery.deliver(content)
        assert client.post.call_count == 2
        # First batch: 10 embeds, second batch: 1 embed
        calls = client.post.call_args_list
        first_body = calls[0].kwargs.get("json") or calls[0][1]["json"]
        second_body = calls[1].kwargs.get("json") or calls[1][1]["json"]
        assert len(first_body["embeds"]) == 10
        assert len(second_body["embeds"]) == 1
