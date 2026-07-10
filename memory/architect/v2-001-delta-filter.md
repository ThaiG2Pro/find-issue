## 2026-07-03 — v2-001-delta-filter: "correctness by omission" — verify the exception hierarchy instead of adding defensive try/except
An error-path AC (AC-V2-001-009: corrupt state file must surface as `Error:` exit 1, filter never
silently disabled) was fully satisfiable by writing ZERO new code. `StateError(Exception)` is NOT a
subclass of `CollectorError`, so it already escapes `_collect_all`'s `except (InvalidRepoError,
NetworkError, CollectorError)` arm, and `cli.py` already maps `StateError -> Error: exit 1`. Adding a
try/except around `is_seen`/`load` would have been the exact anti-pattern the AC forbids (a
mis-scoped catch silently disables the feature). Lesson: for an error-propagation AC, first read the
exception's base class + the existing CLI/except arms and prove the path already works; write an
ADR that decides "add nothing" + a propagation test, rather than reflexively adding handling. The
per-module-one-error-class convention (see delivery-6 lesson above) is what makes this reasoning
reliable — errors are siblings under `Exception`, not a tangled hierarchy.
## 2026-07-03 — v2-001-delta-filter: when two methods share mutable cached state, ordering is a correctness invariant — enforce it structurally, not by comment
`is_seen` and `mark_seen` both read/mutate the same `self._cached` dict. A "delta filter" that runs
after `mark_seen` reads the mutated cache and sees every item as already-seen -> permanently empty
output. The fix that survives future edits is structural: a read-only `_partition_new(items, state)`
helper called inline BEFORE `mark_seen`, with selection happening at the accumulation site — plus a
count-invariant test (`mark_seen` called exactly N times regardless of the filter) as a tripwire.
Generalizes: whenever a new read-path consumes state that an existing write-path mutates in place,
(1) locate the exact write call, (2) place the read before it in the same scope, (3) never re-query
after the write, (4) add a count/identity invariant test that fails if the order is later reversed.
Prefer this over a "must run first" comment, which the next editor will not honor.
