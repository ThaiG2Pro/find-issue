#!/usr/bin/env python3
"""
Shared preToolUse hook: validate a write's target path against the actor's allowed globs.

DUAL-PLATFORM (one source, two hosts):
  • Kiro  — each agent wires its own fs_write hook and passes the agent NAME as argv[1]; the
    target path arrives as tool_input.path. The allow-list is the SINGLE SOURCE OF TRUTH in
    .kiro/agents/<agent>.json → toolsSettings.write.allowedPaths (this hook READS it).
  • Claude Code — ONE PreToolUse(Write|Edit|MultiEdit) hook in .claude/settings.json fires for
    EVERY actor with NO argv; the role arrives in the stdin JSON as `agent_type` (ABSENT for the
    MAIN SESSION), and the target path as tool_input.file_path. Claude agents are .md (no JSON
    allow-list), so this hook falls back to the built-in role policy below — UNLESS a Kiro-style
    .kiro/agents/<role>.json is present (a dual-target project), in which case that JSON wins.

ACTOR → ALLOWED PATHS:
  developer                         → code + tests + config (broad)
  analyst / architect / qa          → openspec/** (+ each role's extra dirs) — NO src/
  onboarder                         → .claude/context/** + openspec/**
  main session (Claude, no agent)   → openspec/** + baton only — the orchestrator NEVER writes code

Glob semantics:
  "dir/**"      → anything under dir/        (prefix match)
  "*.config.ts" → any path ending .config.ts (fnmatch; * spans '/')
  "package.json"→ exact path / basename match

Exit 0 = allowed, Exit 2 = blocked (or misconfigured → deny by default).
Self-test: `python3 check-write-path.py --self-test`.
"""
import json, sys, os, fnmatch


# --- Claude built-in role policy (mirror of the Kiro agent JSON allowedPaths). When a
#     .kiro/agents/<role>.json is present it takes precedence via load_allowed_paths(). ---
_BATON = ["openspec/**", "memory/**", ".kiro/memory/**", ".claude/memory/**"]
_CLAUDE_POLICY = {
    "developer": [
        "src/**", "app/**", "apps/**", "lib/**", "pkg/**", "internal/**", "cmd/**",
        "prisma/**", "migrations/**", "database/**", "db/**",
        "test/**", "tests/**", "e2e/**", "spec/**", "__tests__/**",
        "docker/**", "scripts/**", "config/**", ".github/**",
        "package.json", "composer.json", "pyproject.toml", "Makefile", "Dockerfile",
        "README.md", "*.config.ts", "*.config.js", "*.config.mjs", "*tsconfig.json",
    ] + _BATON,
    "analyst":   ["openspec/**", "docs/knowledge/**"] + _BATON,
    "architect": ["openspec/**", "docs/**"] + _BATON,
    "qa":        ["openspec/**", "test/**", "tests/**", "e2e/**", "spec/**", "__tests__/**"] + _BATON,
    "onboarder": [".claude/context/**", "context/**", "openspec/**", ".kiro/context/**"] + _BATON,
}


def claude_policy(actor):
    """Built-in fallback allow-list for a Claude actor (actor is None for the main session)."""
    if actor in _CLAUDE_POLICY:
        return _CLAUDE_POLICY[actor]
    return list(_BATON)   # main session (None) + any unknown role → spec/baton only, never src/


def resolve_actor(data, argv=None):
    """Kiro wires the agent name as argv[1] → that wins. Else use Claude's stdin `agent_type`
    (ABSENT for the main session). Returns the role name, or None for the Claude main session."""
    argv = sys.argv if argv is None else argv
    if len(argv) > 1 and str(argv[1]).strip() and not str(argv[1]).startswith("-"):
        return str(argv[1]).strip()
    at = (data.get("agent_type") or "").strip()
    return at or None


def find_agent_json(agent: str):
    """Locate <agent>.json. Anchor on this script's dir (reliable regardless of cwd), then fall
    back to cwd-relative locations (and the kit/ source tree for local tests)."""
    if not agent:
        return None
    script_dir = os.path.dirname(os.path.abspath(__file__))  # .../<target>/agents/scripts
    candidates = [
        os.path.join(script_dir, "..", f"{agent}.json"),                       # <target>/agents/<agent>.json
        os.path.join(os.getcwd(), ".kiro", "agents", f"{agent}.json"),
        os.path.join(os.getcwd(), "kit", "targets", "kiro", "agents", f"{agent}.json"),  # kit repo (dev/testing)
        os.path.join(os.getcwd(), "kit", "agents", f"{agent}.json"),           # legacy kit layout
        os.path.join(os.getcwd(), "agents", f"{agent}.json"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def load_allowed_paths(agent: str):
    """Kiro source of truth. Returns the JSON allowedPaths list, or None when no JSON is found
    (→ caller falls back to the Claude built-in policy)."""
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
    if not path:
        return path
    if not os.path.isabs(path):
        return path

    cwd = os.getcwd()
    if path.startswith(cwd + "/"):
        return path[len(cwd) + 1 :]

    markers = [
        "specs/", "openspec/",
        ".kiro/memory/", ".kiro/openspec/", ".kiro/context/", ".kiro/context-map.json",
        ".claude/memory/", ".claude/context/",
        "memory/", "context/", "docs/knowledge/", "docs/",
        "src/", "app/", "apps/", "lib/", "pkg/", "internal/", "cmd/",
        "prisma/", "migrations/", "database/", "db/",
        "test/", "tests/", "e2e/", "spec/", "__tests__/", "docker/", "scripts/", "config/", ".github/",
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


def decide(actor, raw_path):
    """Return (allowed: bool, allowed_list, normalized_path). Shared by main() and the self-test."""
    allowed = load_allowed_paths(actor) if actor else None  # Kiro JSON = source of truth
    if allowed is None:
        allowed = claude_policy(actor)                      # Claude built-in fallback
    if not allowed:
        return (False, allowed, "")
    norm = normalize_path(raw_path)
    return (path_allowed(norm, allowed), allowed, norm)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "--test"):
        return _self_test()

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.stderr.write("BLOCKED: check-write-path could not parse hook input (fail-closed).\n")
        sys.exit(2)

    actor = resolve_actor(data)
    ti = data.get("tool_input") or data.get("toolInput") or {}
    raw_path = ti.get("file_path") or ti.get("path") or data.get("path") or ""
    allowed_ok, allowed, norm = decide(actor, raw_path)

    if allowed is None or (not allowed):
        who = actor or "the main session"
        sys.stderr.write(f"BLOCKED: no write allow-list resolved for '{who}' (fail-closed).\n")
        sys.exit(2)

    if allowed_ok:
        sys.exit(0)

    who = actor or "the main session (orchestrator)"
    sys.stderr.write(
        f"BLOCKED: {who} cannot write to {norm}.\n"
        f"  Allowed: {', '.join(allowed[:6])}{' …' if len(allowed) > 6 else ''}\n"
        f"  Code is written ONLY by the developer agent (S4); other roles write specs/artifacts.\n"
    )
    sys.exit(2)


def _self_test():
    """Vectors: (argv_agent, agent_type, raw_path, expect_allow)."""
    ALLOW, BLOCK = True, False
    vectors = [
        # --- Kiro: agent name via argv, allow-list from .kiro/agents/<agent>.json ---
        ("developer", None, "src/app.ts",                       ALLOW),
        ("developer", None, "tests/app.spec.ts",                ALLOW),
        ("developer", None, "random/elsewhere.txt",             BLOCK),
        ("analyst",   None, "openspec/changes/x/proposal.md",   ALLOW),
        ("analyst",   None, "src/app.ts",                       BLOCK),  # analyst-openspec-only
        ("architect", None, "docs/design.md",                   ALLOW),
        ("architect", None, "src/app.ts",                       BLOCK),
        ("qa",        None, "tests/e2e.spec.ts",                ALLOW),
        ("qa",        None, "src/app.ts",                       BLOCK),
        ("sdlc-full", None, "openspec/changes/x/_state.json",   ALLOW),
        ("sdlc-full", None, "src/app.ts",                       BLOCK),  # orchestrator never writes code
        ("onboarder", None, ".kiro/context/project.md",         ALLOW),
        # --- Claude: role via stdin agent_type (no argv), built-in policy ---
        (None, "developer", "src/app.ts",                       ALLOW),  # developer-allowed
        (None, "developer", "/abs/proj/src/models.py",          ALLOW),  # absolute, normalized
        (None, "developer", "secrets.txt",                      BLOCK),
        (None, None,        "openspec/changes/x/proposal.md",   ALLOW),  # main session writes baton/spec
        (None, None,        "src/app.ts",                       BLOCK),  # MAIN-SESSION-BLOCKED (the core fix)
        (None, None,        "/abs/proj/src/app.ts",             BLOCK),
        (None, "analyst",   "openspec/specs/auth/spec.md",      ALLOW),  # analyst-openspec-only
        (None, "analyst",   "src/app.ts",                       BLOCK),
        (None, "qa",        "tests/unit.spec.ts",               ALLOW),
        (None, "qa",        "src/app.ts",                       BLOCK),
        (None, "onboarder", ".claude/context/project.md",       ALLOW),
        (None, "onboarder", "src/app.ts",                       BLOCK),
    ]
    fails = 0
    for argv_agent, agent_type, raw_path, expect in vectors:
        data = {} if agent_type is None else {"agent_type": agent_type}
        argv = ["check-write-path.py"] + ([argv_agent] if argv_agent else [])
        actor = resolve_actor(data, argv=argv)
        # Pin the allow-list SOURCE per host so the test is deterministic regardless of cwd:
        #   kiro vectors  → the agent JSON (source of truth)
        #   claude vectors→ the built-in role policy (Claude agents have no JSON)
        allowed = load_allowed_paths(actor) if argv_agent else claude_policy(actor)
        allowed_ok = bool(allowed) and path_allowed(normalize_path(raw_path), allowed)
        ok = allowed_ok == expect
        fails += not ok
        tag = "PASS" if ok else "FAIL"
        host = "kiro " if argv_agent else "claude"
        sys.stdout.write(f"  [{tag}] {host} actor={str(argv_agent or agent_type or 'MAIN'):10} "
                         f"{'allow' if allowed_ok else 'BLOCK'} :: {raw_path}\n")
    total = len(vectors)
    sys.stdout.write(f"\n  {total - fails}/{total} passed"
                     f"{'' if not fails else f' — {fails} FAILED'}\n")
    return 1 if fails else 0


if __name__ == "__main__":
    rc = main()
    if rc is not None:
        sys.exit(rc)
