"""Summarizer package — public exports."""

from osspulse.summarizer.client import LiteLLMSummarizer
from osspulse.summarizer.config import SummarizerConfig

__all__ = ["LiteLLMSummarizer", "SummarizerConfig"]
