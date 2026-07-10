## 5 — digest-renderer-5 (S3 done: 2026-06-26)
### Dependencies (from other changes)
- project-foundation: `osspulse.models.SummarizedItem` (`raw: RawItem`, `summary: str`) consumed read-only; `osspulse.ports` (new port added here)
- summarizer-llm-4: consumes the `list[SummarizedItem]` produced by `LiteLLMSummarizer.summarize_items()` (INT-5-001)
- github-collector-2: `RawItem.title`/`url`/`body` may be empty strings — renderer must degrade per field, never assume non-empty (RF-2)
### Shared Decisions
- ADR-001: logic in a pure `render()` free function; `MarkdownDigestRenderer` adapter delegates one line; `Digest` model untouched
- ADR-002: `DigestRenderer(Protocol)` = single `render(items, *, lookback_days) -> str`, structural; no I/O methods (I/O is S6 Delivery)
- ADR-003: determinism via `dict[repo]->dict[group_key]->list`; repos `sorted(key=str.lower)`; fixed `GROUP_ORDER`; input order within group; NO `set`
- ADR-004: unknown `item_type` → single trailing `### Khác (N)` group per repo (never drop an item)
- ADR-005: no openapi.yaml (CLI-only) — cites collector ADR-007, state ADR-004
### Exports (other changes may depend on these)
- `render(items: list[SummarizedItem], *, lookback_days: int) -> str` (`src/osspulse/render/renderer.py`) — pure transform, the digest entry point for S6
- `MarkdownDigestRenderer` (`src/osspulse/render/`) — implements `osspulse.ports.DigestRenderer`
- `osspulse.ports.DigestRenderer` — new role-named Protocol (single `render()` method)
### Constraints Set (apply to subsequent changes)
- Do NOT import `osspulse.github`/`state`/`summarizer`/`cache` from `render/` (AC-5-003, static-tested)
- Renderer is a PURE transform — no file/network/LLM/state I/O; destination selection is S6 Delivery's job (BR-5-002)
- Output is byte-for-byte deterministic — never introduce `set` or unstable ordering (RF-1)
- `DigestRenderer` Protocol frozen at single `render()` — do not add I/O methods in V1
---
