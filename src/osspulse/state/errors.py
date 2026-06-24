class StateError(Exception):
    """Raised for corrupt, unreadable, or unwritable state (AC-3-009, AC-3-010, AC-3-016).

    Mirrors ``ConfigError`` in ``osspulse.config`` — one exception per module, kept in a
    dedicated ``errors`` sub-module so future state adapters (e.g. SQLite) can import it
    without pulling in ``json_store`` (ADR-003).
    """
