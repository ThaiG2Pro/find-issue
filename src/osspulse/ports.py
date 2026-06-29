from typing import Protocol

from osspulse.models import RawItem, SummarizedItem


class GitHubClient(Protocol):
    def fetch_items(self, repo: str, lookback_days: int) -> list[RawItem]: ...


class LLMClient(Protocol):
    def summarize(self, item: RawItem) -> str: ...


class StateStore(Protocol):
    def load(self) -> dict: ...
    def save(self, state: dict) -> None: ...


class SummaryCache(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...


class Delivery(Protocol):
    def deliver(self, content: str) -> None: ...  # AC-6-001, D-1


class DigestRenderer(Protocol):
    def render(self, items: list[SummarizedItem], *, lookback_days: int) -> str: ...
