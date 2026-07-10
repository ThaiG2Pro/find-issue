# Glossary — v2-001-delta-filter

| Term | Definition | Phase | Source |
|------|-----------|-------|--------|
| Delta filter | Pipeline step that suppresses from the digest any collected item already recorded as seen on a *previous* run. Identity-based, config-gated. | S1 | this change |
| Previously-seen item | An item for which `is_seen(repo, item_type, item_id)` returns `true` at the instant BEFORE this run's `mark_seen`. | S1 | AC-V2-001-004 |
| NEW item | An item whose `is_seen` is `false` in the pre-`mark_seen` snapshot — includes items first seen on THIS run. | S1 | AC-V2-001-004 |
| Pre-`mark_seen` snapshot | The set of seen-checks taken before this run records items, so first-seen-this-run items still appear. Chosen over reordering (breaks AC-7-019) or timestamp comparison (second-resolution boundary). | S1 | decision A4 |
| `delta_enabled` | New `Config` bool field (default `true`), parsed from the `[delta] enabled` config key; `false` == V1 no-suppression behavior. | S1 | AC-V2-001-002 |
| Identity-based delta | Suppression keyed on `repo+item_type+item_id`, NOT on content — an edited-but-same-id issue stays suppressed. | S1 | EC-005, Non-Goals |
| Empty-after-filter | State where all collected items are previously-seen; pipeline delivers the "No new items" doc verbatim, never suppresses delivery. | S1 | AC-V2-001-008, A3 |

## S2 terms (append-only; Phase is the LAST column per template)

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| Bool-trap guard | Validation that rejects a non-boolean config value using `type(value) is not bool` (not `isinstance`, because `isinstance(True, int)` is `True`); mirrors `config.py::_validate_lookback`'s `type(value) is not int`. | analyst | BR-V2-001-003 | S2 |
| Seen-snapshot capture | The single act of reading `is_seen` for all collected items BEFORE any `mark_seen` in this run; the resulting set is what the filter partitions on. | analyst | BR-V2-001-001 | S2 |
| StateError surfacing | A corrupt/unreadable state file raises `StateError` (AC-3-009) which the run reports as `Error: <msg>` exit 1 — the filter is never silently disabled. | analyst | AC-V2-001-009, INT-V2-001-001 | S2 |
| Record-vs-render decoupling | Invariant that `delta_enabled` changes which items are summarized/rendered but never which items are recorded via `mark_seen`. | analyst | BR-V2-001-002 | S2 |

## S3 terms (append-only; Phase is the LAST column per template)

| Term | Definition | Defined by | AC/BR ref | Phase |
|------|-----------|-----------|-----------|-------|
| `_partition_new` | Module-private pipeline helper `(items, state) -> (new, seen)`; reads `is_seen` only, called inline in `_collect_all` BEFORE `mark_seen`. Structurally enforces snapshot-before-write ordering. | architect | ADR-001, BR-V2-001-001 | S3 |
| Selection-at-extend | Design pattern: render-list accumulates `new if delta_enabled else items` at the `extend` call, using the pre-`mark_seen` partition result; never re-queries `is_seen` after `mark_seen`. | architect | ADR-004, AC-V2-001-006 | S3 |
| StateError-propagation-by-omission | Correctness-by-not-coding: `StateError` (not a `CollectorError`) escapes `_collect_all`'s except clause and hits the existing CLI mapping; the design forbids adding any try/except around `is_seen`. | architect | ADR-003, AC-V2-001-009 | S3 |
| `_validate_delta` | `config.py` helper mirroring `_validate_lookback`; parses `[delta] enabled` (default true), raises `ConfigError` when `type(value) is not bool`. | architect | ADR-002, BR-V2-001-003 | S3 |
