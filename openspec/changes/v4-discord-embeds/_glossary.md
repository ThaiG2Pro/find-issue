# Glossary — v4-discord-embeds

| Term | Definition | Added by (phase) |
|------|------------|------------------|
| embed | Discord rich card `{title, description, color, footer.text}`; max 10/request, description ≤4096 code points | analyst (S2) |
| use_embeds | `[discord]` opt-in bool config, default false; strict bool-trap validated at load | analyst (S2) |
| stable color | `hashlib(repo_slug) % palette` — deterministic across runs, unlike builtin `hash()` | analyst (S2) |
| _parse_sections | Adapter helper splitting the digest at `## ` line-boundaries → `list[{title, body}]`; returns `[]` when no section (the single fallback trigger) | architect (S3) |
| _repo_color | `int(hashlib.md5(slug).hexdigest(),16) % len(_PALETTE)` → deterministic palette index; NEVER builtin `hash()` | architect (S3) |
| _build_embeds | Maps each section → embed dict; line-splits an over-4096-code-point description into multiple same-title embeds | architect (S3) |
| _batch_embeds | Chunks the embed list into ≤10-embed batches, each POSTed as one `{"embeds":[...]}` request in document order | architect (S3) |
| _PALETTE | Fixed 6-color list of Discord-friendly ints (blurple `0x5865F2`, green, yellow, fuchsia, red, blue) indexed by the stable hash | architect (S3) |
| payload-parameterized POST | Single `_post_one` accepting the JSON body (content vs embeds) so both modes share one timeout + URL-never-leaked error path | architect (S3) |
