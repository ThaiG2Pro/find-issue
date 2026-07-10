"""Crontab managed-block operations + mockable CrontabClient (ADR-007, ADR-008).

``upsert_block`` / ``remove_block`` are pure string transforms — no I/O, fully
unit-testable without touching the real user crontab (RISK-002 mitigation).

``CrontabClient`` wraps the system ``crontab`` command behind a single mockable seam
so tests inject an in-memory buffer instead (ADR-008, INT-V2-002-001).

Marker constants (pinned — AC-V2-002-009):
    BLOCK_START = "# >>> osspulse >>>"
    BLOCK_END   = "# <<< osspulse <<<"

Round-trip guarantee (ADR-007):
    ``remove_block(upsert_block(x, line)) == x``
    for any *x* that had no osspulse block, by the symmetry:
    - upsert appends with a leading ``\\n`` only when *x* is non-empty and does not
      end with ``\\n``;
    - remove strips the exact inclusive [BLOCK_START ... BLOCK_END\\n] region.
"""

from __future__ import annotations

import shutil
import subprocess

from osspulse.schedule.errors import ScheduleError

# ---------------------------------------------------------------------------
# Marker constants (ADR-007, AC-V2-002-009)
# ---------------------------------------------------------------------------

BLOCK_START = "# >>> osspulse >>>"
BLOCK_END = "# <<< osspulse <<<"


# ---------------------------------------------------------------------------
# Pure block transforms (ADR-007)
# ---------------------------------------------------------------------------


def _make_block(cron_line: str) -> str:
    """Return the managed block content (markers + cron line), trailing newline included."""
    return f"{BLOCK_START}\n{cron_line}\n{BLOCK_END}\n"


def upsert_block(current: str, cron_line: str) -> str:
    """Insert or replace the osspulse managed block in *current* crontab text.

    Rules (ADR-007, AC-V2-002-010):
    - If both markers are present → replace the inclusive [start..end] region in-place.
    - If markers are absent → append the block.
      A separator ``\\n`` is prepended whenever *current* is non-empty, ensuring the
      block always starts on its own line.  ``remove_block`` always strips this separator
      when present (``start_idx > 0``), restoring the original byte-for-byte.

      Encoding contract (byte-identical round-trip guarantee):
        - Empty original  → no separator → remove strips nothing before BLOCK_START.
        - Non-empty original (with OR without trailing \\n) → separator ``\\n`` prepended
          → remove strips the ``\\n`` at ``start_idx-1``.
      This means upsert adds ``\\n`` even when original already ends with ``\\n``, which
      is a deliberate choice: the double-\\n is the unambiguous sentinel that remove can
      detect without any lookahead.

    - Lines outside the block are preserved verbatim (AC-V2-002-011).

    Args:
        current: the current crontab text (may be empty string).
        cron_line: the single crontab line to embed inside the block.

    Returns:
        The new crontab text with the managed block installed.
    """
    block = _make_block(cron_line)
    start_idx = current.find(BLOCK_START)
    end_idx = current.find(BLOCK_END)

    if start_idx != -1 and end_idx != -1:
        # Replace existing block in-place (preserves whatever separator already existed).
        block_end_line_end = end_idx + len(BLOCK_END)
        if block_end_line_end < len(current) and current[block_end_line_end] == "\n":
            block_end_line_end += 1
        return current[:start_idx] + block + current[block_end_line_end:]

    # Append: separator \n prepended whenever current is non-empty.
    # (Also when current already ends with \n — the double-\n is the round-trip sentinel.)
    prefix = "\n" if current else ""
    return current + prefix + block


def remove_block(current: str) -> str:
    """Remove the osspulse managed block from *current* crontab text.

    If no block is present → return *current* unchanged (no-op, AC-V2-002-012).

    Round-trip guarantee: ``remove_block(upsert_block(x, line)) == x``
    for any *x* with no pre-existing osspulse block (ADR-007).

    Symmetry with ``upsert_block``:
    - ``upsert_block`` prepends ``\\n`` when *x* is non-empty (``start_idx > 0``).
    - ``remove_block`` strips ``current[start_idx-1]`` (the separator ``\\n``) whenever
      ``start_idx > 0``.  This is unconditional on whether *x* had a trailing ``\\n``.

    Args:
        current: the current crontab text.

    Returns:
        The crontab text with the managed block removed; everything outside preserved.
    """
    start_idx = current.find(BLOCK_START)
    end_idx = current.find(BLOCK_END)

    if start_idx == -1 or end_idx == -1:
        return current  # no block present — no-op (AC-V2-002-012)

    # Strip the separator \n that upsert prepended when appending to non-empty content.
    # upsert ALWAYS prepends \n for non-empty originals, so we ALWAYS strip it here.
    strip_start = start_idx - 1 if start_idx > 0 else start_idx

    # Find end of BLOCK_END line (include its trailing newline).
    block_end_line_end = end_idx + len(BLOCK_END)
    if block_end_line_end < len(current) and current[block_end_line_end] == "\n":
        block_end_line_end += 1

    return current[:strip_start] + current[block_end_line_end:]


# ---------------------------------------------------------------------------
# CrontabClient — mockable subprocess wrapper (ADR-008, AC-V2-002-013)
# ---------------------------------------------------------------------------


class CrontabClient:
    """Wraps the system ``crontab`` command as a single mockable seam.

    ``read()`` — runs ``crontab -l`` and returns the current crontab as a string.
        Normalizes "no crontab for user" (exit 1) to ``""`` (AC-V2-002-013 is the
        *binary-absent* case, not the empty-crontab case).

    ``write(text)`` — pipes *text* to ``crontab -`` via stdin.

    Constructor raises ``ScheduleError`` immediately if the ``crontab`` binary is not
    found on PATH (AC-V2-002-013, ADR-008).
    """

    def __init__(self) -> None:
        if shutil.which("crontab") is None:
            raise ScheduleError(
                "crontab command not found on PATH — cannot install/uninstall schedule"
            )

    def read(self) -> str:
        """Return the current user crontab as a string, or ``""`` if none exists.

        ``crontab -l`` exits 1 with "no crontab for user" when the user has no crontab;
        this is normalised to an empty string (NOT an error).
        """
        result = subprocess.run(  # noqa: S603
            ["crontab", "-l"],  # noqa: S607
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # "no crontab for user" → treat as empty
            stderr = result.stderr.lower()
            if "no crontab" in stderr or result.returncode == 1:
                return ""
            raise ScheduleError(
                f"crontab -l failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout

    def write(self, text: str) -> None:
        """Set the user crontab to *text* by piping it to ``crontab -``."""
        result = subprocess.run(  # noqa: S603
            ["crontab", "-"],  # noqa: S607
            input=text,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ScheduleError(
                f"crontab - failed (exit {result.returncode}): {result.stderr.strip()}"
            )
