#!/usr/bin/env python3
"""
Shared preToolUse hook: keep the shell READ-ONLY for non-developer agents.

WHY THIS EXISTS
  An agent's `write` tool is path-restricted (toolsSettings.write.allowedPaths) and the
  `fs_write` hook (check-write-path.py) enforces those globs. But the `shell` / executeBash
  tool bypasses all of that — it can mutate the filesystem through:
    - redirection to a real file:   echo x > src/app.ts   ·   foo >> file   ·   ... | tee f
    - in-place editors:             sed -i ... · perl -i ...
    - an interpreter eval:          node -e "fs.writeFileSync(...)"  ·  python3 -c "open(...,'w')"
    - file ops:                     cp / mv / rm / touch / mkdir / dd / truncate / ln / install
    - working-tree mutation:        git add/commit/checkout/restore/reset/stash · patch
  Only the DEVELOPER agent (S4) may write code. The orchestrators and the read-phase agents
  must treat the shell as read-only for the filesystem — they run guards (node .kiro/tools/*.mjs),
  openspec, and read-only inspection (cat/grep/ls/…). They write artifacts ONLY via the
  path-guarded `write` tool, never via the shell.

DUAL-PLATFORM (one source, two hosts):
  • Kiro  — each agent wires its own hook and passes the agent NAME as argv[1]:
      "preToolUse": [ { "matcher": "execute_bash",
        "command": "python3 .kiro/agents/scripts/check-shell-command.py <agent>",
        "timeout_ms": 3000 } ]
    (Today only sdlc-full / sdlc-fast wire this; the developer agent has no shell guard.)
  • Claude Code — ONE PreToolUse(Bash) hook in .claude/settings.json fires for EVERY actor with
    NO argv. The acting role arrives in the stdin JSON as `agent_type` — present only when a
    Task-spawned subagent acts, ABSENT when the MAIN SESSION (the orchestrator) acts:
      { "matcher": "Bash",
        "hooks": [ { "type": "command",
          "command": "python3 .claude/agents/scripts/check-shell-command.py" } ] }
    Because the single hook sees all actors, it grants the developer exception INTERNALLY and
    treats the main session (no agent_type) as the read-only orchestrator.

ACTOR → CLASS → POLICY (identical regex denylist for both hosts):
  developer                              → ALLOW (the only code-writing role; full shell)
  orchestrator (Kiro sdlc-*, Claude main)→ READ-ONLY except a single branch/worktree create
  restricted   (analyst/architect/qa/…)  → READ-ONLY, no exceptions

CONTRACT: reads the hook JSON on stdin; exit 0 = allow, exit 2 = block (fail-closed on parse error).
Self-test: `python3 check-shell-command.py --self-test` (covers Kiro + Claude vectors).
"""
import json
import re
import sys

# Harmless redirections that do NOT touch project files — stripped before the write-redirect check.
_DEVNULL = re.compile(r"""(?:\d*|&)>>?\s*/dev/null""")          # 2>/dev/null, >/dev/null, &>/dev/null
_FD_DUP = re.compile(r"""\d*>&\d+""")                            # 2>&1, 1>&2

# Filesystem-mutating constructs. Each (regex, label). Matched against the de-noised command.
_DENY = [
    (re.compile(r"(?<![0-9&])>>?(?!\s*&)"), "output redirection to a file (`>`/`>>`)"),
    (re.compile(r"\btee\b"), "`tee` (writes a file)"),
    (re.compile(r"\bsed\b[^|;&]*?\s-[a-zA-Z]*i"), "`sed -i` (in-place edit)"),
    (re.compile(r"\bperl\b[^|;&]*?\s-[a-zA-Z]*i"), "`perl -i` (in-place edit)"),
    (re.compile(r"\bnode\b[^|;&]*?\s(?:-e|--eval|-p|--print)\b"), "`node -e/--eval/-p` (inline code → arbitrary write)"),
    (re.compile(r"\bpython3?\b[^|;&]*?\s-c\b"), "`python -c` (inline code → arbitrary write)"),
    (re.compile(r"\b(?:node|python3?)\b[^|;&]*?(?:<<|\s-\s*$|\s-\s)"), "interpreter reading stdin/heredoc (→ arbitrary write)"),
    (re.compile(r"\b(?:cp|mv|rm|rmdir|touch|mkdir|dd|truncate|ln|chmod|chown)\b"), "filesystem-mutating command"),
    # `(?:\S+\s+)*?` non-greedily consumes any git global options (`-c x`, `-C /repo`,
    # `--git-dir=…`) smuggled between `git` and the mutating subcommand — closes the bypass.
    (re.compile(r"\bgit\s+(?:\S+\s+)*?(?:add|commit|apply|checkout|restore|reset|stash|rm|mv|push|merge|rebase|tag|clean)\b"), "git working-tree mutation"),
    (re.compile(r"\bgit\s+branch\b[^|;&]*\s-(?:d|D|m|M|c|C|-delete|-move|-copy|-force)\b"), "git branch delete/rename"),
    (re.compile(r"\bpatch\b"), "`patch` (applies a diff)"),
    # Package/dependency managers mutate project files (pyproject.toml, lockfiles, node_modules)
    # — that is developer (S4) work, never the orchestrator's. Read-only subcommands (list/show/
    # version/run-a-readonly-script) are NOT matched.
    (re.compile(r"\b(?:uv|pip|pip3|npm|pnpm|yarn|poetry|cargo|composer|bundle|gem|go|mvn|gradle|dotnet|brew|apt|apt-get|pacman|dnf|yum|pipenv|conda|mamba)\b\s+(?:add|remove|rm|install|uninstall|sync|require|get|update|upgrade|init|build|publish|lock|i|ci)\b"), "package/dependency manager mutation"),
]


# The DEVELOPER (S4) is the only role that may write code — full shell access.
_DEVELOPER = {"developer"}
# Kiro orchestrator agent NAMES. On Claude the orchestrator is the MAIN SESSION (no agent_type →
# actor is None), so None also maps to the orchestrator class below.
_ORCH_AGENTS = {"sdlc-full", "sdlc-fast"}

# The orchestrator may create — and ONLY create — an isolation branch/worktree for a new pipeline
# (sdlc.config.json git.isolation). This is the single, deliberate exception to the "shell is
# read-only for the orchestrator" rule: a branch/worktree create touches NO tracked project file
# (it just moves HEAD / adds a sibling working tree). `git add/commit/checkout <file>/restore/
# reset/merge/...` stay BLOCKED for everyone — the orchestrator still never writes code.
_CMD_SEP = re.compile(r"(?:[;|&]|\$\(|`|<\(|>\()")   # no chaining/substitution may ride along
_BRANCH_CREATE = [
    re.compile(r"^git\s+checkout\s+-b\s+\S"),         # create + switch to a NEW branch
    re.compile(r"^git\s+switch\s+-c\s+\S"),           # modern equivalent of checkout -b
    re.compile(r"^git\s+worktree\s+add\s+\S"),        # create a new working tree (may carry -b)
]


def resolve_actor(data, argv=None):
    """Resolve the acting role across both hosts.
      • Kiro   wires the agent name as argv[1] → that wins.
      • Claude puts `agent_type` in the stdin JSON for a Task subagent; it is ABSENT for the
        main session.
    Returns the role name, or None for the Claude main session (i.e. the orchestrator)."""
    argv = sys.argv if argv is None else argv
    if len(argv) > 1 and str(argv[1]).strip() and not str(argv[1]).startswith("-"):
        return str(argv[1]).strip()
    at = (data.get("agent_type") or "").strip()
    return at or None


def actor_class(actor):
    """Map a resolved actor to a policy class."""
    if actor in _DEVELOPER:
        return "developer"
    if actor is None or actor in _ORCH_AGENTS:
        # Claude main session (None) drives the pipeline === the orchestrator.
        return "orchestrator"
    return "restricted"   # analyst / architect / qa / onboarder + any unknown role


def _is_branch_create(command: str) -> bool:
    """True iff `command` is exactly one branch/worktree-create invocation with no shell chaining
    or command substitution smuggled in."""
    cmd = command.strip()
    if _CMD_SEP.search(cmd):
        return False
    return any(rx.match(cmd) for rx in _BRANCH_CREATE)


def classify(command: str, cls: str = "restricted"):
    """Return a human-readable reason if `command` would mutate the filesystem for an actor of
    policy class `cls`, else None (allowed)."""
    if not command or not command.strip():
        return None
    if cls == "developer":
        return None  # the only code-writing role — full shell access
    if cls == "orchestrator" and _is_branch_create(command):
        return None  # single deliberate exception: isolation branch/worktree create
    # Remove harmless /dev/null + fd-dup redirections so they don't trip the `>` rule.
    denoised = _FD_DUP.sub(" ", _DEVNULL.sub(" ", command))
    for rx, label in _DENY:
        if rx.search(denoised):
            return label
    return None


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-test", "--test"):
        return _self_test()
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.stderr.write("BLOCKED: check-shell-command could not parse hook input (fail-closed).\n")
        return 2
    actor = resolve_actor(data)
    cls = actor_class(actor)
    ti = data.get("tool_input") or data.get("toolInput") or {}
    command = ti.get("command") or ti.get("cmd") or data.get("command") or ""
    reason = classify(command, cls)
    if reason:
        who = actor or "the main session (orchestrator)"
        sys.stderr.write(
            f"BLOCKED: {who} may not write via the shell — {reason}.\n"
            f"  Command: {command.strip()[:200]}\n"
            f"  The shell is READ-ONLY for everyone but the developer agent (S4), the only role that\n"
            f"  writes code. Route the change there; write spec artifacts via the Write tool.\n"
        )
        return 2
    return 0


def _self_test() -> int:
    """Vector table covering both hosts. (argv_agent, agent_type, command, expect_block)."""
    BLOCK, ALLOW = True, False
    vectors = [
        # --- Kiro: agent name via argv ---
        ("sdlc-full", None, "rm -rf build",                 BLOCK),
        ("sdlc-full", None, "echo x > src/app.ts",          BLOCK),
        ("sdlc-full", None, "sed -i s/a/b/ f",              BLOCK),
        ("sdlc-full", None, "git commit -m x",              BLOCK),
        ("sdlc-full", None, "git -c core.hooksPath=/dev/null commit -m x", BLOCK),  # global-opt bypass
        ("sdlc-full", None, "git -C /repo add .",           BLOCK),                 # global-opt bypass
        ("sdlc-full", None, "git --git-dir=/tmp/x reset --hard", BLOCK),            # global-opt bypass
        ("sdlc-full", None, "uv add requests",              BLOCK),
        ("sdlc-full", None, "git checkout -b feat/x",       ALLOW),  # branch-create exception
        ("sdlc-full", None, "git switch -c feat/x",         ALLOW),
        ("sdlc-full", None, "git worktree add ../wt",       ALLOW),
        ("sdlc-full", None, "cat f && rm x",                BLOCK),  # chaining defeats exception
        ("sdlc-fast", None, "openspec list",                ALLOW),
        ("sdlc-full", None, "grep -rn foo .",               ALLOW),
        ("sdlc-full", None, "node .kiro/tools/cpp-guard.mjs",ALLOW),
        # --- Claude: role via stdin agent_type (no argv) ---
        (None, "developer", "rm -rf build",                 ALLOW),  # developer-allowed
        (None, "developer", "uv add requests",              ALLOW),
        (None, "developer", "echo x > src/app.ts",          ALLOW),
        (None, "developer", "git commit -m x",              ALLOW),
        (None, None,        "rm -rf build",                 BLOCK),  # main-session-blocked
        (None, None,        "echo x > src/app.ts",          BLOCK),
        (None, None,        "git checkout -b feat/x",       ALLOW),  # main session == orchestrator
        (None, None,        "grep -rn foo .",               ALLOW),
        (None, "analyst",   "echo x > openspec/p.md",       BLOCK),  # analyst writes via Write tool
        (None, "architect", "rm x",                         BLOCK),
        (None, "qa",        "sed -i s/a/b/ f",              BLOCK),
        (None, "onboarder", "echo x > .claude/context/p.md",BLOCK),
    ]
    fails = 0
    for argv_agent, agent_type, command, expect in vectors:
        data = {} if agent_type is None else {"agent_type": agent_type}
        argv = ["check-shell-command.py"] + ([argv_agent] if argv_agent else [])
        actor = resolve_actor(data, argv=argv)
        blocked = classify(command, actor_class(actor)) is not None
        ok = blocked == expect
        fails += not ok
        tag = "PASS" if ok else "FAIL"
        host = "kiro " if argv_agent else "claude"
        sys.stdout.write(f"  [{tag}] {host} actor={str(argv_agent or agent_type or 'MAIN'):10} "
                         f"{'BLOCK' if blocked else 'allow'} :: {command}\n")
    total = len(vectors)
    sys.stdout.write(f"\n  {total - fails}/{total} passed"
                     f"{'' if not fails else f' — {fails} FAILED'}\n")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
