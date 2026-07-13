import stat
import warnings
from pathlib import Path

import pytest

from osspulse.config import ConfigError, load_config
from osspulse.models import WatchedRepo

ENV = {"GITHUB_TOKEN": "ghp_test"}


def write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_valid_config_returns_config(tmp_path):
    """Valid config returns correct Config object (AC-1-011)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["owner/repo"]\nlookback_days = 14\n')
    cfg = load_config(p, ENV)
    assert cfg.watched_repos == [WatchedRepo("owner", "repo")]
    assert cfg.lookback_days == 14
    assert cfg.github_token == "ghp_test"


def test_default_lookback_days(tmp_path):
    """lookback_days defaults to 7 when absent (AC-1-012)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    cfg = load_config(p, ENV)
    assert cfg.lookback_days == 7


def test_dedupe_warns_and_keeps_first(tmp_path):
    """Duplicate repos are deduped with a warning (AC-1-013)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b", "a/b"]\n')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = load_config(p, ENV)
    assert len(cfg.watched_repos) == 1
    assert any("duplicate" in str(w.message).lower() for w in caught)


def test_unknown_keys_ignored(tmp_path):
    """Unknown keys in config are silently ignored (AC-1-014)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n[unknown_section]\nfoo = "bar"\n')
    cfg = load_config(p, ENV)  # must not raise
    assert cfg.watched_repos == [WatchedRepo("a", "b")]


def test_token_from_env_not_overridden_by_dotenv(tmp_path):
    """Real env token takes precedence (AC-1-015)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    cfg = load_config(p, {"GITHUB_TOKEN": "real_token"})
    assert cfg.github_token == "real_token"


# ---------------------------------------------------------------------------
# Error paths — watchlist
# ---------------------------------------------------------------------------


def test_missing_watchlist_section(tmp_path):
    """Missing [watchlist] raises ConfigError with correct message (AC-1-016)."""
    p = write_toml(tmp_path, "foo = 1\n")
    with pytest.raises(ConfigError, match="missing \\[watchlist\\] section"):
        load_config(p, ENV)


def test_empty_repos_list(tmp_path):
    """Empty repos list raises ConfigError (AC-1-017)."""
    p = write_toml(tmp_path, "[watchlist]\nrepos = []\n")
    with pytest.raises(ConfigError, match="watchlist.repos must not be empty"):
        load_config(p, ENV)


def test_repos_key_absent(tmp_path):
    """[watchlist] present but repos key absent raises ConfigError (AC-1-017)."""
    p = write_toml(tmp_path, "[watchlist]\n")
    with pytest.raises(ConfigError, match="watchlist.repos must not be empty"):
        load_config(p, ENV)


def test_invalid_repo_format(tmp_path):
    """Bad repo format raises ConfigError naming the entry (AC-1-018)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["noslash"]\n')
    with pytest.raises(ConfigError, match="invalid repo 'noslash'"):
        load_config(p, ENV)


# ---------------------------------------------------------------------------
# Error paths — lookback_days
# ---------------------------------------------------------------------------


def test_lookback_days_zero(tmp_path):
    """lookback_days=0 raises ConfigError (AC-1-019)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\nlookback_days = 0\n')
    with pytest.raises(ConfigError, match="lookback_days must be ≥ 1"):
        load_config(p, ENV)


def test_lookback_days_negative(tmp_path):
    """lookback_days=-1 raises ConfigError (AC-1-019)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\nlookback_days = -5\n')
    with pytest.raises(ConfigError, match="lookback_days must be ≥ 1"):
        load_config(p, ENV)


def test_lookback_days_bool_rejected(tmp_path):
    """lookback_days=true is rejected — bool trap (AC-1-020)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\nlookback_days = true\n')
    with pytest.raises(ConfigError, match="lookback_days must be an integer"):
        load_config(p, ENV)


def test_lookback_days_false_rejected(tmp_path):
    """lookback_days=false is rejected — bool trap symmetric case (AC-1-020)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\nlookback_days = false\n')
    with pytest.raises(ConfigError, match="lookback_days must be an integer"):
        load_config(p, ENV)


def test_lookback_days_float_rejected(tmp_path):
    """lookback_days=7.5 is rejected (AC-1-020)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\nlookback_days = 7.5\n')
    with pytest.raises(ConfigError, match="lookback_days must be an integer"):
        load_config(p, ENV)


def test_lookback_days_string_rejected(tmp_path):
    """lookback_days='7' is rejected (AC-1-020)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\nlookback_days = "7"\n')
    with pytest.raises(ConfigError, match="lookback_days must be an integer"):
        load_config(p, ENV)


# ---------------------------------------------------------------------------
# Error paths — token
# ---------------------------------------------------------------------------


def test_missing_github_token(tmp_path):
    """Missing GITHUB_TOKEN raises ConfigError (AC-1-021)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    with pytest.raises(ConfigError, match="GITHUB_TOKEN is required"):
        load_config(p, {})


def test_empty_github_token(tmp_path):
    """Empty/whitespace GITHUB_TOKEN raises ConfigError (AC-1-022)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    with pytest.raises(ConfigError, match="GITHUB_TOKEN is required"):
        load_config(p, {"GITHUB_TOKEN": "   "})


# ---------------------------------------------------------------------------
# Error paths — TOML parsing
# ---------------------------------------------------------------------------


def test_corrupt_toml(tmp_path):
    """Corrupt TOML raises ConfigError with path (AC-1-023)."""
    p = tmp_path / "bad.toml"
    p.write_text("[[invalid")
    with pytest.raises(ConfigError, match="could not parse"):
        load_config(p, ENV)


def test_permission_denied(tmp_path):
    """Unreadable file raises ConfigError (AC-1-024)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    p.chmod(0o000)
    try:
        with pytest.raises(ConfigError, match="cannot read .* permission denied"):
            load_config(p, ENV)
    finally:
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)


# ---------------------------------------------------------------------------
# Warning paths
# ---------------------------------------------------------------------------


def test_lookback_days_over_365_warns(tmp_path):
    """lookback_days>365 emits a warning but succeeds (AC-1-025)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\nlookback_days = 400\n')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = load_config(p, ENV)
    assert cfg.lookback_days == 400
    assert any("365" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# LLM key validation
# ---------------------------------------------------------------------------


def test_remote_llm_requires_api_key(tmp_path):
    """Remote LLM provider without API key raises ConfigError (AC-1-026)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n[llm]\nprovider = "openai"\n')
    with pytest.raises(ConfigError, match="LLM provider 'openai' requires API key"):
        load_config(p, ENV)


def test_remote_llm_with_api_key(tmp_path):
    """Remote LLM provider with API key succeeds (AC-1-026)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n[llm]\nprovider = "openai"\n')
    cfg = load_config(p, {**ENV, "LLM_API_KEY": "sk-test"})
    assert cfg.llm_provider == "openai"
    assert cfg.llm_api_key == "sk-test"


def test_ollama_no_key_required(tmp_path):
    """Ollama provider requires no API key (AC-1-027)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n[llm]\nprovider = "ollama"\n')
    cfg = load_config(p, ENV)
    assert cfg.llm_provider == "ollama"
    assert cfg.llm_api_key is None


# ---------------------------------------------------------------------------
# Delta filter config (AC-V2-001-002, AC-V2-001-006, AC-V2-001-007)
# ---------------------------------------------------------------------------


def test_delta_section_absent_defaults_true(tmp_path):
    """[delta] section absent → delta_enabled defaults to True (AC-V2-001-002)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    cfg = load_config(p, ENV)
    assert cfg.delta_enabled is True


def test_delta_enabled_false(tmp_path):
    """[delta] enabled = false → Config(delta_enabled=False) (AC-V2-001-006)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n[delta]\nenabled = false\n')
    cfg = load_config(p, ENV)
    assert cfg.delta_enabled is False


def test_delta_enabled_true_explicit(tmp_path):
    """[delta] enabled = true is accepted explicitly (AC-V2-001-002)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n[delta]\nenabled = true\n')
    cfg = load_config(p, ENV)
    assert cfg.delta_enabled is True


def test_delta_enabled_non_bool_string_raises(tmp_path):
    """[delta] enabled = "yes" (non-bool) raises ConfigError — bool-trap guard (AC-V2-001-007)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n[delta]\nenabled = "yes"\n')
    with pytest.raises(ConfigError, match="delta.enabled must be a boolean"):
        load_config(p, ENV)


def test_delta_enabled_int_raises(tmp_path):
    """[delta] enabled = 1 (int, not bool) raises ConfigError — isinstance(True, int) trap
    (AC-V2-001-007)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n[delta]\nenabled = 1\n')
    with pytest.raises(ConfigError, match="delta.enabled must be a boolean"):
        load_config(p, ENV)


# ---------------------------------------------------------------------------
# Discord webhook config (AC-V2-005-012..015)
# ---------------------------------------------------------------------------

_DISCORD_URL = "https://discord.com/api/webhooks/123/token"
_DISCORD_ENV = {**ENV, "DISCORD_WEBHOOK_URL": _DISCORD_URL}

_MINIMAL_DISCORD_TOML = '[watchlist]\nrepos = ["a/b"]\n\n[output]\ndestination = "discord"\n'


def test_discord_destination_loads_from_env(tmp_path):
    """destination='discord' + valid env URL → Config with webhook_url set (AC-V2-005-012)."""
    p = write_toml(tmp_path, _MINIMAL_DISCORD_TOML)
    cfg = load_config(p, _DISCORD_ENV)
    assert cfg.output_destination == "discord"
    assert cfg.webhook_url == _DISCORD_URL
    assert cfg.webhook_env == "DISCORD_WEBHOOK_URL"


def test_discord_destination_output_path_irrelevant(tmp_path):
    """output_path is not required / not validated when destination='discord' (AC-V2-005-012)."""
    toml = '[watchlist]\nrepos = ["a/b"]\n\n[output]\ndestination = "discord"\n'
    p = write_toml(tmp_path, toml)
    cfg = load_config(p, _DISCORD_ENV)
    assert cfg.output_destination == "discord"
    # output_path retains default — no error raised
    assert cfg.output_path == "./digest.md"


def test_discord_env_unset_raises(tmp_path):
    """Missing DISCORD_WEBHOOK_URL → ConfigError (AC-V2-005-013)."""
    p = write_toml(tmp_path, _MINIMAL_DISCORD_TOML)
    with pytest.raises(ConfigError, match="DISCORD_WEBHOOK_URL"):
        load_config(p, ENV)  # ENV has no DISCORD_WEBHOOK_URL


def test_discord_env_empty_raises(tmp_path):
    """Empty DISCORD_WEBHOOK_URL → ConfigError (AC-V2-005-013)."""
    p = write_toml(tmp_path, _MINIMAL_DISCORD_TOML)
    with pytest.raises(ConfigError, match="DISCORD_WEBHOOK_URL"):
        load_config(p, {**ENV, "DISCORD_WEBHOOK_URL": "   "})


def test_discord_http_url_raises(tmp_path):
    """http:// webhook URL → ConfigError (AC-V2-005-014)."""
    p = write_toml(tmp_path, _MINIMAL_DISCORD_TOML)
    with pytest.raises(ConfigError, match="https"):
        load_config(p, {**ENV, "DISCORD_WEBHOOK_URL": "http://discord.com/api/webhooks/1/t"})


def test_discord_non_discord_host_raises(tmp_path):
    """Webhook host not in allowlist → ConfigError (AC-V2-005-015)."""
    p = write_toml(tmp_path, _MINIMAL_DISCORD_TOML)
    with pytest.raises(ConfigError, match="discord.com"):
        load_config(p, {**ENV, "DISCORD_WEBHOOK_URL": "https://evil.com/api/webhooks/1/t"})


def test_discord_discordapp_host_accepted(tmp_path):
    """discordapp.com host is in the allowlist (AC-V2-005-015)."""
    p = write_toml(tmp_path, _MINIMAL_DISCORD_TOML)
    url = "https://discordapp.com/api/webhooks/456/token"
    cfg = load_config(p, {**ENV, "DISCORD_WEBHOOK_URL": url})
    assert cfg.webhook_url == url


def test_discord_custom_webhook_env_honored(tmp_path):
    """[output] webhook_env overrides the default env var name (AC-V2-005-012)."""
    toml = (
        '[watchlist]\nrepos = ["a/b"]\n\n'
        '[output]\ndestination = "discord"\nwebhook_env = "MY_DISCORD_URL"\n'
    )
    p = write_toml(tmp_path, toml)
    cfg = load_config(p, {**ENV, "MY_DISCORD_URL": _DISCORD_URL})
    assert cfg.webhook_url == _DISCORD_URL
    assert cfg.webhook_env == "MY_DISCORD_URL"


def test_discord_error_message_does_not_contain_url(tmp_path):
    """ConfigError for bad URL must NOT leak the URL value (AC-V2-005-011)."""
    p = write_toml(tmp_path, _MINIMAL_DISCORD_TOML)
    bad_url = "http://evil.com/api/webhooks/1/supersecrettoken"
    with pytest.raises(ConfigError) as exc_info:
        load_config(p, {**ENV, "DISCORD_WEBHOOK_URL": bad_url})
    assert bad_url not in str(exc_info.value)
    assert "supersecrettoken" not in str(exc_info.value)


def test_invalid_destination_still_rejected(tmp_path):
    """Unknown destination value → ConfigError (AC-6-012)."""
    toml = '[watchlist]\nrepos = ["a/b"]\n\n[output]\ndestination = "email"\n'
    p = write_toml(tmp_path, toml)
    with pytest.raises(ConfigError, match="email"):
        load_config(p, ENV)


# ---------------------------------------------------------------------------
# ETag cache config (AC-V2-007-020, AC-V2-007-021)
# ---------------------------------------------------------------------------


def test_etag_cache_section_absent_defaults_enabled_and_default_path(tmp_path):
    """Absent [etag_cache] section → etag_cache_enabled=True + default path (AC-V2-007-020)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    cfg = load_config(p, ENV)
    assert cfg.etag_cache_enabled is True
    assert cfg.etag_cache_path == "./.osspulse/etags.json"


def test_etag_cache_enabled_false(tmp_path):
    """[etag_cache] enabled = false → etag_cache_enabled=False (AC-V2-007-020)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[etag_cache]\nenabled = false\n')
    cfg = load_config(p, ENV)
    assert cfg.etag_cache_enabled is False


def test_etag_cache_custom_path(tmp_path):
    """[etag_cache] path = custom → etag_cache_path set correctly (AC-V2-007-020)."""
    p = write_toml(
        tmp_path,
        (
            '[watchlist]\nrepos = ["a/b"]\n\n[etag_cache]\n'
            'enabled = true\npath = "/custom/etags.json"\n'
        ),
    )
    cfg = load_config(p, ENV)
    assert cfg.etag_cache_path == "/custom/etags.json"


def test_etag_cache_enabled_non_bool_string_raises(tmp_path):
    """[etag_cache] enabled = "yes" → ConfigError (bool-trap guard, AC-V2-007-021)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[etag_cache]\nenabled = "yes"\n')
    with pytest.raises(ConfigError, match="etag_cache.enabled must be a boolean"):
        load_config(p, ENV)


def test_etag_cache_enabled_int_raises(tmp_path):
    """[etag_cache] enabled = 1 (int, not bool) → ConfigError (isinstance(True, int) trap,
    AC-V2-007-021)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[etag_cache]\nenabled = 1\n')
    with pytest.raises(ConfigError, match="etag_cache.enabled must be a boolean"):
        load_config(p, ENV)


def test_etag_cache_config_error_before_pipeline(tmp_path):
    """Non-boolean etag_cache.enabled raises ConfigError at load time, not inside the pipeline
    (AC-V2-007-021 — fail-fast)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[etag_cache]\nenabled = "true"\n')
    # Confirm exception is raised at load_config call, before any pipeline code runs
    with pytest.raises(ConfigError):
        load_config(p, ENV)


# ---------------------------------------------------------------------------
# Discord embed config — bool-trap (AC-V4-001-008, AC-V4-001-008a)
# ---------------------------------------------------------------------------


def test_discord_use_embeds_absent_defaults_false(tmp_path):
    """Config.toml without [discord] section → discord_use_embeds defaults to False
    (AC-V4-001-008a)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n')
    cfg = load_config(p, ENV)
    assert cfg.discord_use_embeds is False


def test_discord_use_embeds_true(tmp_path):
    """[discord] use_embeds = true → Config.discord_use_embeds is True (AC-V4-001-008)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[discord]\nuse_embeds = true\n')
    cfg = load_config(p, ENV)
    assert cfg.discord_use_embeds is True


def test_discord_use_embeds_string_raises(tmp_path):
    """[discord] use_embeds = "yes" → ConfigError — bool-trap guard (AC-V4-001-008)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[discord]\nuse_embeds = "yes"\n')
    with pytest.raises(ConfigError, match="discord.use_embeds must be a boolean"):
        load_config(p, ENV)


def test_discord_use_embeds_int_raises(tmp_path):
    """[discord] use_embeds = 1 (int, not bool) → ConfigError — isinstance(True, int) trap
    (AC-V4-001-008)."""
    p = write_toml(tmp_path, '[watchlist]\nrepos = ["a/b"]\n\n[discord]\nuse_embeds = 1\n')
    with pytest.raises(ConfigError, match="discord.use_embeds must be a boolean"):
        load_config(p, ENV)
