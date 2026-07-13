# Progress — v4-discord-embeds (V4-001, CR)

| Phase | Agent | Status | Artifacts |
|-------|-------|--------|-----------|
| S1 Req Intake | analyst | ✅ done | proposal.md |
| S2 Func Spec | analyst | ✅ done | specs/delivery/spec.md, tasks.md |
| S3 Design | architect | ✅ done | design.md, _handoff.md, _decisions.jsonl, _glossary.md |

## Scope
`scope=tiny`, `rigor=lite`, `testcase_export=none`, `test_scope=module`. Opt-in Discord
Embeds mode for the existing `DiscordDelivery` adapter. No new dependency, no new trust
boundary — reshapes the JSON body sent to the already-validated webhook.

## Summary
- 9 ACs (AC-V4-001-001, 002, 002b, 003, 004, 005, 006, 007, 008, 008a — all [CONFIRMED]),
  7 BRs (BR-V4-001-001..007), 1 INT (INT-V4-001-001).
- Modifies `delivery` capability: ADDED embed requirements + MODIFIED "Destination
  selection is config-driven" (adds `[discord] use_embeds`).
- `openspec change validate` → PASS.

## Key decisions
- Color determinism via `hashlib` (NOT builtin `hash()` — process-salted, breaks idempotency).
- Embed limits enforced in code points: ≤10 embeds/request (batch), ≤4096 chars/description (line-split).
- `deliver(content: str)` signature UNCHANGED; embeds parsed from Markdown in-adapter (no upstream import).
- Plain-text fallback for no-`##`-section digests and unformattable embeds.

## Next Action
🔍 DESIGN REVIEW required. Return to SDLC orchestrator → "approve s3" (runs cross-artifact-audit).
Then developer /s4. Do NOT self-run /s4.
