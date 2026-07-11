## 2026-07-11 — v3-github-actions: a "run it on CI / GitHub Actions" CR hides three traps the raw ask never names
Shipping a committed Actions workflow that "persists state.json via git commit" is never just a YAML
file. Three latent requirements bite at S1:
(1) **Gitignore trap** — the state file (and often `config.toml`) is gitignored for local dev, so the
literal "commit state.json" is impossible without `git add -f` AND a committed secret-free CI config.
Grep `.gitignore` for the persisted path BEFORE writing ACs. Do NOT un-ignore the paths (leaks local
dev state/config into every commit).
(2) **Non-PyPI install** — if the tool isn't published, the workflow must install from the checked-out
source; an existing "generate a workflow" command (here V2-002's `schedule --github-actions`) may emit
`pip install <tool>` that silently fails on CI. Always contrast the committed artifact against any
generator template.
(3) **Cross-runner concurrency** — a per-machine `fcntl` single-instance lock does NOT span two GitHub
runners (manual + scheduled overlap racing the committed state). Needs a CI-level `concurrency:` group.
Plus the always-latent scheduling pair from V2-002: UTC cron TZ (spec `0 1 * * *` not `0 8 * * *` for
08:00 UTC+7) and secretless artifacts (`${{ secrets.* }}` only). And the no-op-commit guard: a
no-new-items run leaves state byte-identical, so `git commit` errors "nothing to commit" and reddens
the job unless you branch on `git diff --quiet`.
