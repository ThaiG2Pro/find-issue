from dataclasses import dataclass


@dataclass(frozen=True)
class WatchedRepo:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class Config:
    watched_repos: list[WatchedRepo]
    lookback_days: int = 7
    github_token: str = ""
    llm_provider: str | None = None
    llm_api_key: str | None = None


@dataclass(frozen=True)
class RawItem:
    repo: str
    item_type: str  # "issue" | "discussion" | "release"
    item_id: str
    title: str
    body: str
    url: str
    created_at: str


@dataclass(frozen=True)
class SummarizedItem:
    raw: RawItem
    summary: str


@dataclass(frozen=True)
class Digest:
    repo: str
    items: list[SummarizedItem]
