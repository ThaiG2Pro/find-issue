# Release Notes — V2-005 (v0.8.0)
Date: 2026-07-09
Branch: feature/V2-005-push-delivery

## Summary

Discord webhook push delivery. Digest tự động POST lên Discord channel sau mỗi lần chạy.

## Files to update (developer task)

### 1. CHANGELOG.md — prepend trước `## [0.7.0]`

```
## [0.8.0] — 2026-07-09

### Added (v2-005-push-delivery)

- **Discord webhook delivery** (`destination = "discord"`): digest POSTs to a Discord
  channel webhook after every run. Configure via `[output] destination = "discord"` in
  config.toml and `DISCORD_WEBHOOK_URL` in .env (AC-V2-005-001).
- **Smart 2000-char split**: long digests split automatically at `## repo` section
  boundaries first, then line, then hard char-slice — every message ≤ 2000 Unicode code
  points (Discord API limit) (AC-V2-005-004..007).
- **Configurable webhook env var**: `webhook_env` key overrides the env var name
  (AC-V2-005-012).
- **Security**: webhook URL never in logs/errors — DeliveryError uses status codes and
  exception type names only (AC-V2-005-011, STRIDE T1).
- **SSRF guard**: https + discord.com/discordapp.com host enforced at config-load
  (AC-V2-005-014..015).
- **10s timeout**: DeliveryError on timeout/network failure → exit 1 (AC-V2-005-010).

### Config snippet (for CHANGELOG)

[output]
destination = "discord"
# webhook_env = "DISCORD_WEBHOOK_URL"   # optional override

# .env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN

### Known limitations (for CHANGELOG)

- Partial multi-message delivery: messages 1..k-1 already sent if message k fails;
  no rollback (RISK-1, accepted — retry/backoff in V4).
- pipeline.py discord branch (291-294) not covered by pipeline tests; adapter fully
  tested (24 tests).
```

### 2. README.md — bảng `.env` variables, thêm row sau `STATE_PATH`

```
| `DISCORD_WEBHOOK_URL` | When `destination = "discord"` | Discord webhook URL. Create at: channel ⚙️ → Integrations → Webhooks → Copy URL. |
```

### 3. README.md — `[output]` config block, thêm comment sau `output_path`

```toml
# destination = "discord" — POST to Discord webhook.
# Requires DISCORD_WEBHOOK_URL env var (https://discord.com/... or discordapp.com/...).
# webhook_env = "MY_VAR"  # optional: override the env var name
```

### 4. .env.example — append sau REDIS_URL block

```bash
# ── Discord delivery (optional) ───────────────────────────────────────────────
# Webhook URL for Discord push delivery (destination = "discord" in config.toml).
# Create at: Discord server → channel ⚙️ → Integrations → Webhooks → New Webhook → Copy URL
# Must be https://discord.com/api/webhooks/... or https://discordapp.com/...
# DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/replace_with_id/replace_with_token
```

### 5. pyproject.toml — bump version

```
version = "0.8.0"
```

### 6. Git ops

```bash
git checkout feature/V2-005-push-delivery
git add CHANGELOG.md README.md .env.example pyproject.toml
git commit -m "release: v0.8.0 — Discord webhook push delivery (V2-005)"
git push -u origin feature/V2-005-push-delivery
gh pr create \
  --title "V2-005: Discord webhook push delivery (v0.8.0)" \
  --body "Adds Discord webhook delivery adapter. See CHANGELOG for details."
```

### 7. Post-merge archive

```bash
openspec archive v2-005-push-delivery
```

## Verification

- [ ] `uv run pytest tests/ -q` → 103+ passed, 0 failed
- [ ] `uv run ruff check .` → clean
- [ ] `grep "0.8.0" pyproject.toml CHANGELOG.md` → both match
- [ ] `.env.example` has DISCORD_WEBHOOK_URL placeholder
- [ ] README table has DISCORD_WEBHOOK_URL row
