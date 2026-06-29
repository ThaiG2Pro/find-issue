"""FileDelivery adapter — atomic UTF-8 file write (ADR-002, AC-6-004..006, AC-6-014..020)."""

import os
import tempfile
from pathlib import Path

from osspulse.delivery.errors import DeliveryError


class FileDelivery:
    """Concrete Delivery adapter that writes content atomically to a file.

    Implements the ``osspulse.ports.Delivery`` Protocol structurally (no subclassing).
    """

    def __init__(self, output_path: str) -> None:
        self._output_path = output_path

    def deliver(self, content: str) -> None:
        """Write *content* atomically to the configured path as UTF-8 (AC-6-004/005/018).

        Sequence (ADR-002, Flow 2):
        1. mkstemp in target.parent   — missing parent → FileNotFoundError (AC-6-014/015)
        2. fdopen + write + fsync     — ENOSPC/perm → OSError (AC-6-016)
        3. os.replace                 — atomic same-fs rename (AC-6-005/018/019)
        4. finally: unlink on failure — existing target never clobbered (AC-6-006)

        Does NOT mkdir the parent (AC-6-014).
        """
        target = Path(self._output_path)
        tmp_name: str | None = None
        try:
            fd, tmp_name = tempfile.mkstemp(dir=target.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, target)
            tmp_name = None  # renamed successfully; skip unlink
        except OSError as exc:
            raise DeliveryError(f"cannot write digest to {target}: {exc}") from exc
        finally:
            if tmp_name is not None:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass  # best-effort cleanup
