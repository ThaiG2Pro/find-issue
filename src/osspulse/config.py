import re
import tomllib
import warnings
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv

from osspulse.models import Config, WatchedRepo

# Single source of truth for the ``owner/name`` repo identifier (ADR-006, AC-2-014,
# BR-2-011). Promoted to a public constant so the GitHub Collector reuses the exact same
# pattern instead of redefining a second regex that could drift.
REPO_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")


class ConfigError(Exception):
    pass


def _validate_repos(watchlist: dict) -> list[WatchedRepo]:
    repos_raw = watchlist.get("repos")
    if not repos_raw:
        raise ConfigError("watchlist.repos must not be empty")
    seen: dict[str, WatchedRepo] = {}
    for entry in repos_raw:
        if not REPO_PATTERN.match(entry):
            raise ConfigError(f"invalid repo '{entry}': expected 'owner/name'")
        if entry in seen:
            warnings.warn(f"duplicate repo '{entry}' ignored", stacklevel=2)
        else:
            owner, name = entry.split("/", 1)
            seen[entry] = WatchedRepo(owner=owner, name=name)
    return list(seen.values())


def _validate_lookback(watchlist: dict) -> int:
    value = watchlist.get("lookback_days", 7)
    if type(value) is not int:  # noqa: E721 — bool trap: isinstance(True, int) is True
        raise ConfigError("lookback_days must be an integer")
    if value <= 0:
        raise ConfigError("lookback_days must be ≥ 1")
    if value > 365:
        warnings.warn(f"lookback_days={value} is large (> 365); proceeding anyway", stacklevel=2)
    return value


def _resolve_token(env: Mapping[str, str]) -> str:
    token = env.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise ConfigError("GITHUB_TOKEN is required")
    return token


def _resolve_llm(data: dict, env: Mapping[str, str]) -> tuple[str | None, str | None]:
    llm_section = data.get("llm", {})
    provider = llm_section.get("provider")
    if not provider:
        return None, None
    if provider.lower() != "ollama":
        key_var = llm_section.get("api_key_env", "LLM_API_KEY")
        api_key = env.get(key_var, "").strip()
        if not api_key:
            raise ConfigError(f"LLM provider '{provider}' requires API key")
        return provider, api_key
    return provider, None


def load_config(config_path: Path, env: Mapping[str, str] | None = None) -> Config:
    # Step 1: load .env (does not override real env vars)
    load_dotenv()
    if env is None:
        import os

        env = os.environ

    # Step 2: read + parse TOML
    try:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"cannot read {config_path}: file not found")
    except PermissionError:
        raise ConfigError(f"cannot read {config_path}: permission denied")
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"could not parse {config_path}: {exc}")

    # Step 3: watchlist section
    watchlist = data.get("watchlist")
    if watchlist is None:
        raise ConfigError("missing [watchlist] section")

    # Step 4: repos
    watched_repos = _validate_repos(watchlist)

    # Step 5: lookback_days
    lookback_days = _validate_lookback(watchlist)

    # Step 6: token
    github_token = _resolve_token(env)

    # Step 7: LLM
    llm_provider, llm_api_key = _resolve_llm(data, env)

    # Step 8: optional [state] section
    state_section = data.get("state", {})
    state_path: str = state_section.get("state_path", "./.osspulse/state.json")

    # Steps 9-10: unknown keys ignored, return Config
    return Config(
        watched_repos=watched_repos,
        lookback_days=lookback_days,
        github_token=github_token,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        state_path=state_path,
    )
