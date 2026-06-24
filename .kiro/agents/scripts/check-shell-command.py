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

WIRING (in <agent>.json, alongside the existing fs_write entry):
  "preToolUse": [
    { "matcher": "execute_bash",
      "command": "python3 .kiro/agents/scripts/check-shell-command.py <agent>",
      "timeout_ms": 3000 }
  ]
  NOTE: the matcher string is the executeBash tool's hook id. If a future Kiro build renames it,
  update the matcher — verify with the self-test at the bottom of this file.

CONTRACT: reads the hook JSON on stdin; exit 0 = allow, exit 2 = block (fail-closed on parse error).
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
    (re.compile(r"\bgit\s+(?:add|commit|apply|checkout|restore|reset|stash|rm|mv|push|merge|rebase|tag|clean)\b"), "git working-tree mutation"),
    (re.compile(r"\bpatch\b"), "`patch` (applies a diff)"),
    # Package/dependency managers mutate project files (pyproject.toml, lockfiles, node_modules)
    # — that is developer (S4) work, never the orchestrator's. Read-only subcommands (list/show/
    # version/run-a-readonly-script) are NOT matched.
    (re.compile(r"\b(?:uv|pip|pip3|npm|pnpm|yarn|poetry|cargo|composer|bundle|gem|go|mvn|gradle|dotnet|brew|apt|apt-get|pacman|dnf|yum|pipenv|conda|mamba)\b\s+(?:add|remove|rm|install|uninstall|sync|require|get|update|upgrade|init|build|publish|lock|i|ci)\b"), "package/dependency manager mutation"),
]


def classify(command: str):
    """Return a human-readable reason if the command would mutate the filesystem, else None."""
    if not command or not command.strip():
        return None
    # Remove harmless /dev/null + fd-dup redirections so they don't trip the `>` rule.
    denoised = _FD_DUP.sub(" ", _DEVNULL.sub(" ", command))
    for rx, label in _DENY:
        if rx.search(denoised):
            return label
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.stderr.write("BLOCKED: check-shell-command could not parse hook input (fail-closed).\n")
        return 2
    agent = sys.argv[1] if len(sys.argv) > 1 else "this agent"
    ti = data.get("tool_input") or data.get("toolInput") or {}
    command = ti.get("command") or ti.get("cmd") or data.get("command") or ""
    reason = classify(command)
    if reason:
        sys.stderr.write(
            f"BLOCKED: {agent} may not write via the shell — {reason}.\n"
            f"  Command: {command.strip()[:200]}\n"
            f"  The shell is READ-ONLY for non-developer agents. Code is written ONLY by the\n"
            f"  developer agent (S4). Route the change there; write artifacts via the `write` tool.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
