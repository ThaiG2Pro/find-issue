"""StdoutDelivery adapter — writes digest to stdout (ADR-003, AC-6-007..009)."""

import sys
from typing import TextIO


class StdoutDelivery:
    """Concrete Delivery adapter that writes content to stdout (no subclassing required).

    Does NOT catch ``BrokenPipeError`` — that is handled at the CLI top level (ADR-003).
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def deliver(self, content: str) -> None:
        """Write *content* + one trailing newline to stdout (AC-6-007/008).

        Does NOT catch ``BrokenPipeError`` — propagates to the CLI top-level handler.
        """
        self._stream.write(content)
        self._stream.write("\n")
        self._stream.flush()
