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
