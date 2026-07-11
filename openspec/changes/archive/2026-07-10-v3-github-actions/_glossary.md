# Glossary — v3-github-actions (ticket V3-002)

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| State persistence (git commit-back) | Committing `.osspulse/state.json` back into the repo after a CI run so the next stateless runner starts from the recorded seen-state | analyst | AC-V3-002-003 | S2 |
| `[skip ci]` | Commit-message marker that, together with a GITHUB_TOKEN-authored push, prevents the persistence commit from re-triggering the workflow | analyst | AC-V3-002-005 | S2 |
| Force-add | `git add -f .osspulse/state.json` — stages the state file despite it being gitignored, so CI can commit it while local dev keeps ignoring `.osspulse/` | analyst | AC-V3-002-003 | S2 |
| No-op commit guard | The persistence step detecting a clean tree (unchanged state) and completing successfully without an empty commit or a failed job | analyst | AC-V3-002-004 | S2 |
| Concurrency group | Actions `concurrency:` (cancel-in-progress:false) that serializes an overlapping manual + scheduled run so they never race the committed state file | analyst | AC-V3-002-007 | S2 |
| Committed CI config | A secret-free `config.toml` present in the runner (config.toml is normally gitignored) so `osspulse run` has valid config on CI | analyst | AC-V3-002-011 | S2 |
| UTC cron | Actions `schedule.cron` is evaluated in UTC; `0 1 * * *` = 01:00 UTC = 08:00 UTC+7 | analyst | AC-V3-002-001 | S2 |
| Secretless artifact | The workflow/config referencing secrets only via `${{ secrets.* }}`, never inlining a raw value | analyst | AC-V3-002-010 | S2 |
| Clean-tree guard (`git diff --cached --quiet`) | Branching on the STAGED diff after `git add -f` so an unchanged-state run no-ops with exit 0 (never an empty commit or red job) — checks cached, not unstaged, because the force-add stages the file | architect | AC-V3-002-004 | S3 |
| Install-from-source | `uv pip install --system -e .` on the runner — installs osspulse from the checked-out repo, NOT `pip install osspulse` (not on PyPI) | architect | AC-V3-002-002 | S3 |
