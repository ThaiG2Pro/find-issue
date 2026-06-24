import dataclasses

import pytest

from osspulse.models import Config, WatchedRepo


def test_watched_repo_full_name():
    """WatchedRepo.full_name returns 'owner/name' (AC-1-011)."""
    repo = WatchedRepo(owner="facebook", name="react")
    assert repo.full_name == "facebook/react"


def test_watched_repo_frozen():
    """WatchedRepo is immutable (AC-1-011)."""
    repo = WatchedRepo(owner="org", name="repo")
    with pytest.raises(dataclasses.FrozenInstanceError):
        repo.owner = "other"  # type: ignore[misc]


def test_config_defaults():
    """Config defaults lookback_days=7, token empty, no LLM (AC-1-011)."""
    cfg = Config(watched_repos=[WatchedRepo("a", "b")])
    assert cfg.lookback_days == 7
    assert cfg.github_token == ""
    assert cfg.llm_provider is None
    assert cfg.llm_api_key is None
