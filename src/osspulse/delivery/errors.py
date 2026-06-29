class DeliveryError(Exception):
    """Raised for unwritable file destinations (AC-6-016, BR-6-009).

    Mirrors ``StateError`` in ``osspulse.state.errors`` — one exception per module,
    kept in a dedicated sub-module so future adapters can import it without pulling
    in ``file_delivery`` (ADR-006).
    """
