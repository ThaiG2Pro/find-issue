"""Unit tests for DiscordDelivery adapter (AC-V2-005-001..003, 008..011)."""

import sys
from unittest.mock import MagicMock

import httpx
import pytest

from osspulse.delivery.discord_delivery import DiscordDelivery
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
