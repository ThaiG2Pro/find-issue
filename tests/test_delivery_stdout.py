"""Unit tests for StdoutDelivery (AC-6-007, AC-6-008, AC-6-009)."""

import io

import pytest

from osspulse.delivery.stdout_delivery import StdoutDelivery


def test_stdout_writes_content_plus_one_newline(AC="AC-6-007, AC-6-008"):
    """Delivers content + exactly one trailing newline, nothing else (AC-6-007, AC-6-008)."""
    buf = io.StringIO()
    StdoutDelivery(stream=buf).deliver("# Digest\nhello")
    assert buf.getvalue() == "# Digest\nhello\n"


def test_stdout_single_newline_not_double():
    """No double newline appended when content already ends with newline (AC-6-008)."""
    buf = io.StringIO()
    StdoutDelivery(stream=buf).deliver("line\n")
    assert buf.getvalue() == "line\n\n"  # content + 1 added newline (spec: 1 trailing newline)


def test_stdout_empty_content_writes_single_newline():
    """Empty string delivers as a single newline (AC-6-008)."""
    buf = io.StringIO()
    StdoutDelivery(stream=buf).deliver("")
    assert buf.getvalue() == "\n"


def test_stdout_raises_on_broken_stream(AC="AC-6-009"):
    """BrokenPipeError propagates — not swallowed by StdoutDelivery (AC-6-009)."""

    class _BrokenStream(io.RawIOBase):
        def write(self, _):
            raise BrokenPipeError("broken pipe")

    with pytest.raises(BrokenPipeError):
        StdoutDelivery(stream=_BrokenStream()).deliver("content")


def test_stdout_raises_on_closed_stream():
    """Writing to a closed stream propagates the error (AC-6-009)."""
    buf = io.StringIO()
    buf.close()
    with pytest.raises(ValueError):  # closed StringIO raises ValueError on write
        StdoutDelivery(stream=buf).deliver("content")
