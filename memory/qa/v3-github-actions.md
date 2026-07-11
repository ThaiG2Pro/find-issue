## 2026-07-11 — v3-github-actions: bash `||`/`&&` left-associativity trap in CI persist scripts

Shell `A || B && C` is parsed as `(A || B) && C` in bash (equal-precedence, left-to-right),
NOT `A || (B && C)` as often intuitively assumed. In the pattern:

```
git diff --cached --quiet || git commit -m '...' && git push
```

When diff is quiet (exit 0 = no changes): `(exit_0 || commit)` = exit 0, then `exit_0 && git push`
→ `git push` runs on EVERY no-change run. For a git-commit-back CI pattern, this means a spurious
push API call each time. Effect is benign (push fast-forwards, exits 0) but it's not the no-op
the author intended. The dev report incorrectly claimed `A || (B && C)` semantics.

**Fix pattern**: use a subshell to enforce grouping: `git diff --cached --quiet || (git commit -m '...' && git push)`

**QA lesson**: For any inline `||`/`&&` chain in CI persist scripts, explicitly verify bash
associativity rather than trusting dev comments about precedence. Simulate with `bash -c 'true || echo X && echo Y'`.
