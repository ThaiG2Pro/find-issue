"""Schedule-module error class (AC-V2-002-006, AC-V2-002-013, AC-V2-002-016).

Mirrors ``StateError`` / ``DeliveryError`` — one exception per module, kept in a
dedicated ``errors`` sub-module so future adapters can import it without pulling in
the full schedule package (ADR-005, delivery-6 memory).
"""


class ScheduleError(Exception):
    """Raised for fatal schedule failures: invalid cron expr, crontab missing,
    unwritable --output, mutually-exclusive flags, or secret-leak backstop.

    Surfaces at the CLI as ``Error: <msg>`` on stderr + exit 1.
    See also: ``LockHeldError`` in ``osspulse.lock`` for benign lock contention (exit 0).
    """
