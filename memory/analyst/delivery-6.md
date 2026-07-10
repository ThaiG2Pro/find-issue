## 2026-06-29 — delivery-6: OpenSpec parses requirement description only up to the first comma — put SHALL/MUST in the first clause
`openspec validate --strict` extracts each `### Requirement:` description as the text from the heading
to the first comma/line break and checks it contains SHALL or MUST. A requirement whose opening sentence
front-loads a parenthetical list before the verb (e.g. "When X cannot be written (missing dir, perms,
disk full), the stage SHALL surface…") FAILS validation because the truncated description ("When X cannot
be written (missing dir") has no SHALL — even though the full paragraph does. Fix: write the first clause
so SHALL/MUST appears before any comma ("The stage SHALL surface … This applies when …"). Cheap to avoid
up front; otherwise it's a late round-trip at the validate step.
## 2026-06-29 — delivery-6: a stale port stub can silently mismatch the realized upstream contract
The `Delivery` port was stubbed early as `send(self, digest: Digest)` but the actual upstream stage (S5
renderer) was later realized to emit a `str`, not a `Digest`. Always diff the consuming port's signature
against what the producing stage actually returns (read the producer's real return type, not the port
stub) — a port written before its neighbor is implemented tends to drift. Flag the correction as an
explicit MODIFIED-capability decision so the architect updates ports.py + wiring, rather than the
developer quietly adapting at S4.
