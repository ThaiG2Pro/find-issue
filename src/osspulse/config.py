import re
import tomllib
import warnings
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

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


def _validate_max_items_per_type(watchlist: dict) -> int:
    """Parse the optional ``[watchlist] max_items_per_type`` key (AC-V4-002-005, AC-V4-002-005b).

    Bool-trap + strict-int guard mirrors ``_validate_lookback``: ``type(value) is not int``
    rejects bool/float/str; value < 1 is invalid. Default 10.
    """
    value = watchlist.get("max_items_per_type", 10)
    if type(value) is not int:  # noqa: E721 — bool trap: isinstance(True, int) is True
        raise ConfigError("max_items_per_type must be an integer")
    if value < 1:
        raise ConfigError("max_items_per_type must be ≥ 1")
    return value


def _validate_delta(data: dict) -> bool:
    """Parse the optional ``[delta] enabled`` key, defaulting to ``True`` (AC-V2-001-002).

    Bool-trap guard mirrors ``_validate_lookback``: ``type(value) is not bool`` (not
    ``isinstance``, since ``isinstance(True, int)`` is ``True``) — rejects non-bool values
    like ``"yes"`` or ``1`` fail-fast at load time (AC-V2-001-007).
    """
    delta_section = data.get("delta", {})
    value = delta_section.get("enabled", True)
    if type(value) is not bool:  # noqa: E721 — bool trap, see _validate_lookback
        raise ConfigError("delta.enabled must be a boolean")
    return value


def _validate_discord_use_embeds(data: dict) -> bool:
    """Parse the optional ``[discord] use_embeds`` key, default ``False`` (AC-V4-001-008/008a).

    Bool-trap guard mirrors ``_validate_delta``: ``type(value) is not bool`` rejects
    non-bool values like ``"yes"`` or ``1`` fail-fast at load time (AC-V4-001-008).
    Absent ``[discord]`` section or absent ``use_embeds`` key → ``False`` (AC-V4-001-008a).
    """
    discord_section = data.get("discord", {})
    value = discord_section.get("use_embeds", False)
    if type(value) is not bool:  # noqa: E721 — bool trap, see _validate_lookback
        raise ConfigError("discord.use_embeds must be a boolean")
    return value


def _validate_etag_cache(data: dict) -> tuple[bool, str]:
    """Parse the optional ``[etag_cache]`` section (AC-V2-007-020/021).

    Returns ``(etag_cache_enabled, etag_cache_path)``.

    Bool-trap guard mirrors ``_validate_delta``: ``type(value) is not bool`` rejects
    non-bool values like ``"yes"`` or ``1`` fail-fast at load time (AC-V2-007-021).
    Absent section → defaults: ``enabled=True``, ``path="./.osspulse/etags.json"``.
    """
    _DEFAULT_ETAG_PATH = "./.osspulse/etags.json"
    etag_section = data.get("etag_cache", {})
    value = etag_section.get("enabled", True)
    if type(value) is not bool:  # noqa: E721 — bool trap: isinstance(True, int) is True
        raise ConfigError("etag_cache.enabled must be a boolean")
    path = etag_section.get("path", _DEFAULT_ETAG_PATH)
    return value, str(path)


def _resolve_token(env: Mapping[str, str]) -> str:
    token = env.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise ConfigError("GITHUB_TOKEN is required")
    return token


def _resolve_llm(data: dict, env: Mapping[str, str]) -> tuple[str | None, str | None, str | None]:
    llm_section = data.get("llm", {})
    provider = llm_section.get("provider")
    model = llm_section.get("model") or None
    if not provider:
        return None, None, None
    if provider.lower() != "ollama":
        key_var = llm_section.get("api_key_env", "LLM_API_KEY")
        api_key = env.get(key_var, "").strip()
        if not api_key:
            raise ConfigError(f"LLM provider '{provider}' requires API key")
        return provider, api_key, model
    return provider, None, model


def _resolve_discord_url(output_section: dict, env: Mapping[str, str]) -> tuple[str, str]:
    """Resolve + validate the Discord webhook URL from env (AC-V2-005-012..015).

    Returns (webhook_url, webhook_env_name).
    Raises ConfigError on missing/empty env var, non-https scheme, or non-Discord host.
    Never logs the URL value (T1/AC-V2-005-011).
    """
    _DISCORD_HOSTS = frozenset({"discord.com", "discordapp.com"})

    env_name: str = output_section.get("webhook_env", "DISCORD_WEBHOOK_URL")
    url = env.get(env_name, "").strip()
    if not url:
        raise ConfigError(
            f"output.destination='discord' requires {env_name} env var to be set"
        )  # AC-V2-005-013 — no URL in message (it's empty anyway)

    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ConfigError(
            "output.destination='discord': webhook URL must use https scheme"
        )  # AC-V2-005-014 — no URL value in message
    if parsed.hostname not in _DISCORD_HOSTS:
        raise ConfigError(
            "output.destination='discord': webhook host must be discord.com or discordapp.com"
        )  # AC-V2-005-015 — no URL value in message

    return url, env_name


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

    # Step 5b: max_items_per_type (AC-V4-002-005)
    max_items_per_type = _validate_max_items_per_type(watchlist)

    # Step 6: token
    github_token = _resolve_token(env)

    # Step 7: LLM
    llm_provider, llm_api_key, llm_model = _resolve_llm(data, env)

    # Step 8: optional [state] section
    state_section = data.get("state", {})
    state_path: str = state_section.get("state_path", "./.osspulse/state.json")

    # Step 9: [output] section — fail-fast validation (ADR-004, AC-6-010..013, AC-V2-005-012..015)
    output_section = data.get("output", {})
    output_destination: str = output_section.get("destination", "file")
    if output_destination not in ("file", "stdout", "discord"):
        raise ConfigError(
            f"output.destination must be 'file', 'stdout', or 'discord', got {output_destination!r}"
        )
    output_path: str = output_section.get("output_path", "./digest.md")
    if output_destination == "file" and (
        not isinstance(output_path, str) or not output_path.strip()
    ):
        raise ConfigError("output.output_path must be a non-empty string when destination='file'")

    # Discord webhook — resolve + validate env var (ADR-003, AC-V2-005-012..015)
    webhook_url: str | None = None
    webhook_env: str = "DISCORD_WEBHOOK_URL"
    if output_destination == "discord":
        webhook_url, webhook_env = _resolve_discord_url(output_section, env)

    # Step 10: optional [delta] section — fail-fast bool-trap validation (AC-V2-001-002/007)
    delta_enabled = _validate_delta(data)

    # Step 11: optional [etag_cache] section — fail-fast bool-trap validation (AC-V2-007-020/021)
    etag_cache_enabled, etag_cache_path = _validate_etag_cache(data)

    # Step 12: optional [discord] section — fail-fast bool-trap validation (AC-V4-001-008/008a)
    discord_use_embeds = _validate_discord_use_embeds(data)

    return Config(
        watched_repos=watched_repos,
        lookback_days=lookback_days,
        github_token=github_token,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        state_path=state_path,
        output_destination=output_destination,
        output_path=output_path,
        delta_enabled=delta_enabled,
        webhook_url=webhook_url,
        webhook_env=webhook_env,
        etag_cache_enabled=etag_cache_enabled,
        etag_cache_path=etag_cache_path,
        discord_use_embeds=discord_use_embeds,
        max_items_per_type=max_items_per_type,
    )
