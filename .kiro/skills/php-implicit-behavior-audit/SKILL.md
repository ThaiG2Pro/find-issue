---
name: php-implicit-behavior-audit
description: >
  Audit PHP source for implicit behaviors (unbounded recursion, shared tables,
  nullable columns, narrow catch blocks, hidden side effects) and classify each
  as CONTRACT (must preserve in Node port) or ACCIDENT (free to redesign).
  Use during S1 Step 4d / S2 mid-flow when feature ports PHP logic to Node.js.
---

# PHP Implicit Behavior Audit

## Why This Exists

PHP source != spec. PHP has emergent behavior from language semantics, framework
defaults, and historical accidents that the original developer never documented.
When porting to Node.js, every implicit behavior must be classified:

- **CONTRACT** → POS clients / downstream consumers depend on it → must preserve exactly
- **ACCIDENT** → side effect of how the code happened to be written → free to redesign

If unclassified, ambiguity bleeds into S3 (architect must guess) or S4 (developer
must ask) — re-work cost 5-25× vs catching in S1/S2 (cost 1×).

Two real cases this skill catches early (from SPEC-04 reserve flow):

1. **Unbounded recursion**: PHP `Cache::lock` retry uses `return $this->reserved($request)`
   without a depth cap. PHP-FPM stack-overflows under sustained contention → 500.
   Node port adds 3-retry cap → forced to invent response shape that PHP never had.
   This skill flags it BEFORE S3, asking: is the 500 a contract POS observes, or
   accidental side effect?

2. **`voucher_reserved.warehouse_id` NULL**: Merchant `VoucherHelper::reserved()`
   omits the column; warehouse `VoucherReservedService::reservedCodeWarehouse()` sets
   it. Same table, different writers, no comment explaining the convention. Node
   port asks: is NULL a contract (downstream uses `WHERE warehouse_id IS NULL`)
   or just an accident?

## When to Use

- **S1 Step 4d** — after edge-case-enumerator, when feature ports PHP logic
- **S2 mid-flow** — if writing ACs reveals previously undefined PHP behavior
- **Re-run** if user surfaces new ambiguity during clarification round

**Skip when**: pure new feature with no PHP source to port.

## Input

- PHP source files relevant to the feature (use `SOURCE_CODE_ANALYSIS.md` to locate)
- Vendor packages under `vendor/dayonevn/` (often contain merchant logic — check both
  `app/` AND `vendor/dayonevn/`)
- DB schema for any tables the feature writes to (note shared tables)
- `docs/knowledge/SPEC-*.md` for the endpoint
- Existing `docs/40-mapping/01-method-mapping.md` if available

## Audit Checklist (5 categories)

For each PHP behavior the spec inherits, run all 5 checks:

### 1. Recursion / Loop Termination
- Q: Does this recursion or loop have an **explicit** termination cap?
- Q: What is the **documented response** when termination is reached?
- Q: If unbounded — is the implicit "fail" path (stack overflow → 500, infinite
  loop → timeout → 504) part of contract or accident?
- Search hints: `usleep`, `sleep`, `while(true)`, `return $this->{methodName}(`,
  recursive calls
- Output: CONTRACT (cap value + fail response shape) or ACCIDENT (Node free to
  define both cap and response)

### 2. Shared Table / Cross-Endpoint Writes
- Q: Is this DB table written by **multiple endpoints**? (grep for `INSERT` / model
  `::create([` across `app/` and `vendor/dayonevn/`)
- Q: Per column, which endpoint(s) **own writes**? Which leave it at default/NULL?
- Q: Are there downstream consumers (analytic queries, exports, reports, monitoring
  dashboards) that depend on per-endpoint shape?
- Search hints: `WHERE {col} IS NULL`, `WHERE {col} IS NOT NULL`, reports/exports
  in `app/Services/Report/`, monitoring in `app/Services/Monitoring/`
- Output: Ownership matrix per column. CONTRACT if downstream `WHERE IS NULL`
  exists; ACCIDENT otherwise.

### 3. Nullable Column Invariants
- Q: For each nullable column the feature touches, what does NULL **mean** per caller?
- Q: Is NULL a valid business state, or just "this caller didn't fill it"?
- Q: Does any code do `WHERE col IS NULL` to **distinguish callers**?
- Output: Invariant per caller. CONTRACT if disambiguation queries exist; ACCIDENT
  otherwise.

### 4. Catch Block Scope
- Q: Does catch handle one specific exception type, or broad `\Exception` / `\Throwable`?
- Q: What exceptions **bubble past** this catch? Where do they end up?
- Q: Is the bubble path part of contract (e.g., HTTP 500 surfaced to client with
  specific shape, vs swallowed silently)?
- Search hints: `catch (RequestException`, `catch (Exception`, `catch (\Throwable`,
  uncaught patterns near `DB::beginTransaction`
- Output: Error propagation diagram. Note exception types caught vs silently bubbled
  vs explicitly rethrown.

### 5. Side Effects in Critical Section
- Q: Inside locks (`Cache::lock`, `lockForUpdate`) or transactions (`DB::transaction`,
  `DB::beginTransaction`), are there HTTP / Redis / Cache calls?
- Q: Are these idempotent? What happens on **partial failure** (DB committed but
  side effect failed, or vice versa)?
- Q: Is the side effect **order** (DB → cache invalidate → event fire) part of contract?
- Search hints: HTTP clients (`Http::`, `GuzzleHttp`, `curl_`), event dispatch
  (`broadcastVouchersUsedEvent`, `event(`), cache writes inside transaction blocks
- Output: Side-effect inventory with idempotency note + ordering requirement.

## Output Format

Append this section to `proposal.md` / the spec deltas (S1 §3.5 — between assumptions and edge cases):

```markdown
## §3.5 PHP Implicit Behavior Audit

### Recursion / Loop Termination
- B-{ticket}-001 [CONTRACT]: {behavior summary}
  - Source: `{file}:{line}`
  - Reason: {why contract — cite downstream that depends on it}
  - Action: {how Node port must preserve}

- B-{ticket}-002 [ACCIDENT]: {behavior summary}
  - Source: `{file}:{line}`
  - Reason: {why accident — no downstream depends on it}
  - Action: {Node design decision — typically defer to architect /s3 with note}

### Shared Table / Cross-Endpoint Writes
- B-{ticket}-003 [CONTRACT]: ...

### Nullable Column Invariants
- B-{ticket}-004 [ACCIDENT]: ...

### Catch Block Scope
- B-{ticket}-005 [CONTRACT]: ...

### Side Effects in Critical Section
- B-{ticket}-006 [CONTRACT]: ...

### Unresolved — Feed to clarification-generator
- B-{ticket}-007 [UNCLEAR]: {behavior}
  - Source: `{file}:{line}`
  - Question: {what to ask}
  - Resolver: {DBA / BA / Ops / downstream team name}
  - Block level: {S1 (must resolve) / S2 (can defer) / S3 (architect can decide)}
```

## Rules

- Every behavior gets **EXACTLY ONE** label: `[CONTRACT]`, `[ACCIDENT]`, or `[UNCLEAR]`
- Every entry MUST cite source `file:line` (use vendor path if applicable)
- Every `[UNCLEAR]` MUST name a concrete resolver (not "team")
- `[UNCLEAR]` items feed into `clarification-generator` (count toward R9 max-5 budget)
- `[CONTRACT]` items become AC tags `[CONFIRMED]` with PHP source reference in the AC
- `[ACCIDENT]` items become AC tags `[ASSUMED]` with explicit Node design decision
- Behavior IDs follow `B-{ticket_id}-{NNN}` format — referenced from ACs

## Decision Heuristics

When unsure between CONTRACT and ACCIDENT, prefer **UNCLEAR** if:
- The PHP behavior would surface differently in Node (e.g., stack overflow → 500
  vs. caught Error → 200/999): UNCLEAR — ask BA/Ops if 500 was observed in production
- Multiple downstream systems exist that you can't audit cheaply: UNCLEAR — escalate
- Behavior is a "feature" of how PHP-FPM works (not Laravel app code): UNCLEAR

Lean toward **ACCIDENT** when:
- Behavior is purely internal (no client-visible effect)
- Behavior is a Laravel/PHP framework default that Node has equivalent for
- No code anywhere does `WHERE` / `IF` checks that depend on the behavior

Lean toward **CONTRACT** when:
- POS clients have observable response (status code, body shape, header)
- Downstream queries/reports filter by the behavior
- Same shape appears in 2+ unrelated PHP code paths (= deliberate convention)

## Anti-patterns

- ❌ Classifying without reading actual PHP source (use `read` tool, not memory)
- ❌ Assuming "PHP did X = X is contract" without checking downstream
- ❌ Classifying everything as CONTRACT (overly defensive — leads to copying bugs
  like unbounded recursion into Node)
- ❌ Classifying everything as ACCIDENT (cavalier — may break POS clients silently)
- ❌ Skipping the audit when feature "looks simple" — these 5 categories trigger most
  on simple-looking features
- ❌ Forgetting to check `vendor/dayonevn/` — merchant logic often lives there, not
  in `app/`

## Cross-References

- Output entries `[UNCLEAR]` → feed to `clarification-generator` skill
- Output entries `[CONTRACT]` → analyst writes ACs with source-citing PHP file:line
- Output entries `[ACCIDENT]` → analyst tags `[ASSUMED]` in AC; architect picks
  design in /s3
- See `SOURCE_CODE_ANALYSIS.md` for PHP source map
- See `docs/40-mapping/01-method-mapping.md` for known PHP method → Node file mapping
