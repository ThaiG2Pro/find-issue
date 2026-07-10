## 2026-07-06 — v2-003-releases: when an endpoint's SORT key differs from the inclusion/filter key, early-stop must key on the SORT field, not the filter field

The GitHub `/releases` endpoint returns items newest-first by `created_at` and supports no
`sort=published`, but the requirement filters by `published_at`. The safe early-stop pagination
keys the STOP condition on `created_at` (the actual sort order — so the "everything after is older"
guarantee holds) and the INCLUDE condition on `published_at` (the requirement) as a per-item filter.
Keying the stop on the filter field is a silent data-loss bug: under created-desc ordering the first
low-`published_at` item can appear before a later high-`published_at` one, so the loop stops too
early and drops valid items unpredictably. Generalizes to ANY paginated upstream where the server's
sort key ≠ the field you filter on (issues sorted by created but filtered by updated, events sorted
by id but filtered by timestamp, etc.): (1) find the endpoint's ACTUAL sort key, (2) early-stop on
that key's cutoff, (3) filter/skip individual items on the requirement key, (4) accept + TEST the
residual window where the two keys diverge (an item whose sort-field is out-of-window but
filter-field is in-window) rather than pretending it can't happen. If the residual miss is
unacceptable, the only correct fix is to disable early-stop and full-scan (bounded by a max-items
cap) — but that is a requirement-level tradeoff (page budget vs completeness), not a silent
implementation choice. Reuse the existing single-field cutoff helper (`_parse_created`) against BOTH
fields rather than writing a second parser.

## 2026-07-06 — v2-003-releases: "add a second fetch to an isolated per-repo loop" — wrap ONLY the new fetch, keep one partition + one mark_seen

When a per-repo loop that already isolates one fetch (issues) gains a second fetch (releases) under
the SAME failure-isolation contract, the naive move — one try/except covering both — loses the
first fetch's already-collected results if the second raises. Read the isolation AC literally: if it
says "items already collected for that repo survive", the second fetch needs its OWN narrow inner
try/except (catch recoverable errors → yield `[]`), while fatal (`AuthError`) and terminal
(`RateLimitError`) errors are deliberately kept OUT of the inner catch so they still reach the outer
fatal/partial-deliver arms. Crucially, concatenate both fetches' results and run the existing
state-write sequence ONCE (`_partition_new` before `mark_seen`, `mark_seen` on the FULL list) — do
NOT introduce a second `mark_seen` site or a deferred partition, which reopens the
partition-after-mark_seen ordering bug (v2-001 R1). A count-invariant test (`mark_seen` called once
per repo with `len(a)+len(b)` items) is the durable tripwire. Generalizes: adding a source to a
shared isolation+dedup loop is an "extend the list, guard the new I/O, keep the write path
single-call" change — never a "duplicate the write path" change.

## 2026-07-06 — v2-003-releases: inner-guard specs must call out fatal subclasses explicitly

When writing a design spec for a narrow `try/except` inner guard, always include a line like:
> "Note: `AuthError` and `RateLimitError` are subclasses of `CollectorError`; do NOT include
> `CollectorError` base in the catch tuple — it would silently swallow fatal/terminal errors."

The v2-003 design listed `(InvalidRepoError, NetworkError, CollectorError)` without this note.
The developer correctly caught the bug via a test, but had to introduce an undocumented deviation.
One sentence in the design spec would have prevented the deviation entirely.

**Rule of thumb:** any `except` that catches a base class in a hierarchy where some subclasses
must propagate requires an explicit "except these subclasses" note in the spec.
