# Memory — architect — v3-github-actions (V3-002)

## 2026-07-11 — v3-github-actions: CI git-commit-back persistence pattern

Persisting a gitignored state file back from a stateless CI runner is a three-part
structural pattern, not a single command:
1. **`git add -f <path>`** — force-add because the path is gitignored (keep `.gitignore`
   intact; un-ignoring leaks local dev state into every commit — reject it).
2. **`git diff --cached --quiet` guard** — branch on the STAGED diff, not `git diff`
   (unstaged). The force-add already staged the file, so an unstaged check always reads
   "clean" and never commits. Unchanged run → no-op exit 0, never `--allow-empty`.
3. **Two independent loop guards** — `[skip ci]` in the message AND the fact that a push
   authored by the default `GITHUB_TOKEN` does not re-trigger `on: schedule`/`on: push`.
   Spec both; don't rely on one.

Plus: `permissions: contents: write` only (push 403s without it; broader scope violates
least privilege), and a `concurrency` group to serialize overlapping manual + scheduled
runs — a per-machine `fcntl` lock does NOT span separate runners.

Also: when a V-earlier generator template exists (V2-002 `schedule --github-actions`),
contrast it explicitly in the design — this CR differs on install source
(`uv pip install -e .` vs `pip install osspulse`), write permission, and persistence — so
the developer hand-authors rather than reusing a template that would fail on CI.
