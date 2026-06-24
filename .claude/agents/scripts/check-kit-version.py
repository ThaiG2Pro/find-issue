#!/usr/bin/env python3
"""
Version-drift detector (MIGRATION.md §7 Q4). Fail-silent, read-only, cheap.

Compares the kitVersion recorded in the installed manifest (.claude/.kit-manifest.json or
.kiro/.kit-manifest.json) against the kit version that is "available", and prints ONE warning
line if they differ — catching the "forgot to re-run init / reload after updating the kit"
trap. If the available version cannot be resolved, it prints nothing (never noisy).

Wiring:
  • Claude Code — a SessionStart hook in .claude/settings.json:
      python3 .claude/agents/scripts/check-kit-version.py
  • Kiro — an agentSpawn line (optional).

Resolving the AVAILABLE version (best-effort, in order; first hit wins):
  1. $KIRO_SDLC_KIT_VERSION             — explicit override (CI / wrapper sets it)
  2. $KIRO_SDLC_KIT_HOME/package.json   — a local checkout/global install of the kit
  3. (otherwise) give up silently — we will not guess or hit the network in a session hook.

Always exits 0 (advisory only; never blocks a session).
"""
import json
import os
import sys


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def installed_version():
    """kitVersion from whichever platform manifest exists (prefer the one passed as argv[1])."""
    hint = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    candidates = []
    if hint in (".claude", ".kiro", "claude", "kiro"):
        d = hint if hint.startswith(".") else "." + hint
        candidates.append(os.path.join(d, ".kit-manifest.json"))
    candidates += [
        os.path.join(".claude", ".kit-manifest.json"),
        os.path.join(".kiro", ".kit-manifest.json"),
    ]
    for c in candidates:
        m = read_json(c)
        if isinstance(m, dict) and m.get("kitVersion"):
            return m["kitVersion"], c
    return None, None


def available_version():
    env_v = (os.environ.get("KIRO_SDLC_KIT_VERSION") or "").strip()
    if env_v:
        return env_v
    home = (os.environ.get("KIRO_SDLC_KIT_HOME") or "").strip()
    if home:
        pkg = read_json(os.path.join(home, "package.json"))
        if isinstance(pkg, dict) and pkg.get("version"):
            return str(pkg["version"]).strip()
    return None


def main():
    installed, src = installed_version()
    if not installed:
        return 0  # kit not installed here (or unversioned legacy manifest) — nothing to compare
    avail = available_version()
    if not avail:
        return 0  # cannot resolve the available version → stay silent (the §Q4 "when reachable" clause)
    if avail != installed:
        sys.stderr.write(
            f"⚠ SDLC kit drift: installed {installed} ({src}) but {avail} is available — "
            f"re-run `npx kiro-sdlc-init . --force` and reload the session.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
