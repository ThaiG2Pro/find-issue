from typing import Protocol

from osspulse.models import Digest, RawItem


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
    def send(self, digest: Digest) -> None: ...
