"""Summarizer error hierarchy — token-safe by construction (ADR-008, AC-4-012).

Every message carries item identity (repo/item_type/item_id) + a static reason only.
The LLM API key, prompt content, and body text are NEVER interpolated into an error.
"""


class SummarizerError(Exception):
    """Base for all Summarizer failures. Messages = item identity + static reason only."""


class SummarizationFailed(SummarizerError):
    """LLM produced no usable summary (empty/whitespace output); triggers skip (EC-012)."""
