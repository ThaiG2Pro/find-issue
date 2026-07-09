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
    state_path: str = "./.osspulse/state.json"  # AC-3-013
    output_destination: str = "file"  # AC-6-010, BR-6-007
    output_path: str = "./digest.md"  # AC-6-010, BR-6-007
    delta_enabled: bool = True  # AC-V2-001-002
    webhook_url: str | None = None  # AC-V2-005-012, BR-V2-005-005; resolved from env at load
    webhook_env: str = "DISCORD_WEBHOOK_URL"  # AC-V2-005-012; name of the env var


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
