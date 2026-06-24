#!/usr/bin/env python3
"""
Shared preToolUse hook: validate fs_write paths against the agent's allowed globs.

SINGLE SOURCE OF TRUTH: the allowed write paths live in each agent's
`.kiro/agents/<agent>.json` under `toolsSettings.write.allowedPaths` (glob form).
This hook READS that list — it does NOT keep its own copy. Edit the agent JSON to
change write permissions; the hook follows automatically.

Glob semantics (matched here, mirroring how allowedPaths reads):
  "dir/**"         → anything under dir/         (prefix match)
  "*.config.ts"    → any path ending .config.ts  (fnmatch; * also spans '/')
  "package.json"   → exact path / basename match

Usage: echo '{"tool_input":{"path":"..."}}' | python3 check-write-path.py <agent_name>
Exit 0 = allowed, Exit 2 = blocked (or misconfigured → deny by default).
"""
import json, sys, os, fnmatch


def find_agent_json(agent: str):
    """Locate <agent>.json. Anchor on this script's dir (reliable regardless of cwd),
    then fall back to cwd-relative locations (and the kit/ source tree for local tests)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))  # .../.kiro/agents/scripts
    candidates = [
        os.path.join(script_dir, "..", f"{agent}.json"),               # .kiro/agents/<agent>.json
        os.path.join(os.getcwd(), ".kiro", "agents", f"{agent}.json"),
        os.path.join(os.getcwd(), "kit", "agents", f"{agent}.json"),   # kit repo (dev/testing)
        os.path.join(os.getcwd(), "agents", f"{agent}.json"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def load_allowed_paths(agent: str):
    path = find_agent_json(agent)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return None
    return (cfg.get("toolsSettings", {}).get("write", {}) or {}).get("allowedPaths")


def normalize_path(path: str) -> str:
    """Convert absolute path to project-relative by stripping the workspace root."""
    if not os.path.isabs(path):
        return path

    cwd = os.getcwd()
    if path.startswith(cwd + "/"):
        return path[len(cwd) + 1 :]

    markers = [
        "specs/", "openspec/", ".kiro/memory/", ".kiro/openspec/", ".kiro/context/",
        ".kiro/context-map.json", "docs/",
        "src/", "app/", "apps/", "lib/", "pkg/", "internal/", "cmd/",
        "prisma/", "migrations/", "database/", "db/",
        "test/", "tests/", "spec/", "__tests__/", "docker/", "scripts/", "config/", ".github/",
    ]
    for marker in markers:
        idx = path.find("/" + marker)
        if idx != -1:
            return path[idx + 1 :]

    # Fallback: project-root file → match by basename against exact/suffix globs.
    return os.path.basename(path)


def path_allowed(path: str, patterns) -> bool:
    for pat in patterns:
        if pat.endswith("/**"):
            base = pat[:-3]  # "src/**" -> "src"
            if path == base or path.startswith(base + "/"):
                return True
        elif any(ch in pat for ch in "*?["):
            if fnmatch.fnmatch(path, pat):
                return True
        elif path == pat:
            return True
    return False


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: check-write-path.py <agent_name>\n")
        sys.exit(2)

    agent = sys.argv[1]
    allowed = load_allowed_paths(agent)
    if not allowed:
        # Deny by default: a misconfigured/missing allowlist must not silently permit writes.
        sys.stderr.write(
            f"BLOCKED: no toolsSettings.write.allowedPaths found for '{agent}' "
            f"(.kiro/agents/{agent}.json)\n"
        )
        sys.exit(2)

    data = json.load(sys.stdin)
    raw_path = data.get("tool_input", {}).get("path", "")
    path = normalize_path(raw_path)

    if path_allowed(path, allowed):
        sys.exit(0)

    sys.stderr.write(f"BLOCKED: {agent} cannot write to {path}")
    sys.exit(2)


if __name__ == "__main__":
    main()
