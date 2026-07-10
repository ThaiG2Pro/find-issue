## 2026-07-02 — v2-001-delta-filter: spec-delta requirements can reference BR/INT IDs that are never defined — S2 must add the definition blocks
S1 wrote `> Business rules: BR-V2-001-001..004` and `> Integration: INT-V2-001-001` in the
requirement front-matter but no `## Business Rules` / `## Integration Points` definition block
existed anywhere in the change. `openspec validate` passes regardless (it does not cross-check that
referenced BR/INT IDs are defined), and spec-auditor's 6 checks don't cover it either — so a
dangling reference sails through both gates and only bites the architect/QA who go looking for the
rule text. Fix: at S2, before the SPEC LOCK gate, grep the spec delta for every `BR-`/`INT-` id in
`> Business rules:`/`> Integration:` lines and confirm each has a matching definition in a
`## Business Rules` / `## Integration Points` block (mirror the archived scheduler-cli-7 format).
Cheap to add up front; otherwise it's a design-time round-trip.
## 2026-07-02 — v2-001-delta-filter: _glossary.md column order must keep Phase LAST or cpp-guard misreads the phase
The glossary template mandates `Term | Definition | Defined by | AC/BR ref | Phase` with Phase as
the LAST column because cpp-guard reads the trailing table cell as the row's phase. A prior phase
had written the table as `Term | Definition | Phase | Source` (Phase 3rd, Source last), so the
trailing cell was "Source" — cpp-guard would read e.g. the source ref as the phase. Because the
glossary is append-only (write-path hook blocks edits that drop existing `##`/rows), you cannot
silently fix the old header. Safe fix: append new rows under a fresh `## S2 terms` subheading using
the correct template column order (Phase last) so at least one row has a valid trailing phase cell,
and leave the legacy rows untouched. Better: catch the column-order drift at S1 when the table is
first created.
