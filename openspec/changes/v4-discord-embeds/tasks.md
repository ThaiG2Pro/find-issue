## 1. Implementation

- [ ] 1.1 Add `Config.discord_use_embeds: bool = False` to `src/osspulse/models.py` (AC-V4-001-008a)
- [ ] 1.2 Add `_validate_discord_use_embeds(data)` to `src/osspulse/config.py` — parse optional `[discord] use_embeds`, strict `type(v) is not bool` guard, default `False`; wire into `load_config` + `Config(...)` (AC-V4-001-008, AC-V4-001-008a)
- [ ] 1.3 Add a fixed 5–6 color palette + stable `hashlib`-based `_color_for_repo(slug)` helper in `discord_delivery.py` — never builtin `hash()` (AC-V4-001-002, BR-V4-001-003)
- [ ] 1.4 Add `_build_embeds(content)` — split at `## ` (reuse section-split logic), map each section → embed {title=header minus `## `, description=body, color, footer.text=`OSS Pulse • {ts}`}; split over-4096-char descriptions by line; batch ≤ 10 embeds/request (AC-V4-001-001, AC-V4-001-003, AC-V4-001-004, BR-V4-001-002/004)
- [ ] 1.5 Add `use_embeds: bool = False` ctor param to `DiscordDelivery`; in `deliver()` branch to embed POST (`{"embeds": [...]}`) when true, else existing plain-text path; fall back to plain text when no `## ` section or embed can't be formed (AC-V4-001-005, AC-V4-001-006, BR-V4-001-005)
- [ ] 1.6 Embed POST reuses the existing timeout + URL-never-leaked error path; fatal on any request failure, no rollback (AC-V4-001-007, BR-V4-001-006)
- [ ] 1.7 Wire `use_embeds=config.discord_use_embeds` into `DiscordDelivery` construction in the pipeline/CLI (INT-V4-001-001)

## 2. Tests (module scope)

- [ ] 2.1 config: `[discord] use_embeds` true/false/absent → flag; non-bool → `ConfigError` (AC-V4-001-008, AC-V4-001-008a)
- [ ] 2.2 embed mode: two sections → 2-embed body, title/description/color/footer correct (AC-V4-001-001)
- [ ] 2.3 color determinism: same slug → same color across two invocations; palette membership (AC-V4-001-002)
- [ ] 2.4 limits: >4096-char description split by line (code points, not bytes); 11+ sections → ≥2 requests ≤10 embeds (AC-V4-001-003, AC-V4-001-004)
- [ ] 2.5 fallback: use_embeds=false → plain `{"content"}`; "No new items" doc → plain-text POST (AC-V4-001-005, AC-V4-001-006)
- [ ] 2.6 failure: embed POST non-2xx/timeout → `DeliveryError`, URL absent from message (AC-V4-001-007)

## 3. Gate

- [ ] 3.1 `openspec change validate "v4-discord-embeds"` passes
- [ ] 3.2 Module-scope test + lint/static-analysis green
