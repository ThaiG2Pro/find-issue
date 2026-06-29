# Glossary — delivery-6

| Term | Definition | Added by | Phase |
|------|------------|----------|-------|
| Delivery (S6) | Terminal pipeline sink: consumes the rendered Markdown digest **string** from S5 and writes it to a destination (file/stdout in V1). Decoupled from S2/S4 and from domain models. | analyst | S2 |
| `deliver(content: str)` | The V1 `Delivery` port method (replaces the stale `send(digest: Digest)` stub). Takes the rendered string, returns None. AC-6-001, D-1. | analyst | S2 |
| `[output]` config section | New TOML section selecting the destination: `destination` ("file"\|"stdout", default "file") and `output_path` (default "./digest.md", file mode only). AC-6-010..013, BR-6-007. | analyst | S2 |
| Atomic delivery | File write via temp-file-in-same-dir → fsync → `os.replace`; a crash never leaves a partial/corrupt digest. AC-6-005/006, BR-6-003. | analyst | S2 |
| stdout delivery | Destination mode writing the digest (+1 trailing newline) to `sys.stdout` only; no file written, `output_path` ignored. AC-6-007/008, BR-6-006. | analyst | S2 |
| Deterministic overwrite | Re-delivering the same content overwrites byte-identically; never appends, never duplicates. AC-6-018/019, BR-6-011. | analyst | S2 |
| `FileDelivery` | S6 file adapter: writes the digest atomically (temp-in-target-dir → fsync → `os.replace`) as UTF-8 to `output_path`; raises `DeliveryError` on any write failure. ADR-002. | architect | S3 |
| `StdoutDelivery` | S6 stdout adapter: writes `content` + one trailing newline to `sys.stdout` (UTF-8); broken-pipe handled at the CLI top level, not here. ADR-003. | architect | S3 |
| `DeliveryError` | Per-module exception (mirrors `StateError`) for file-write failures; surfaces as `Error: <message>` on stderr + exit 1; message names the offending path. ADR-006. | architect | S3 |
| Broken-pipe locus | The decision that `BrokenPipeError` (e.g. `osspulse run \| head`) is caught at the CLI top level + `os.dup2` stdout→devnull, never inside the adapter — covers the interpreter's final flush. ADR-003, AC-6-009. | architect | S3 |
