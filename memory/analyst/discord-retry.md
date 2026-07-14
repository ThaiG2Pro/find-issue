# analyst memory — discord-retry

## 2026-07-14 — discord-retry: adding retry to a "fail-fatally-on-first-error" delivery adapter MODIFIES the fatal requirement (delivery-side twin of the v3-llm-throttle lesson)

The v2-005 Discord push spec had BR-V2-005-004 with an explicit "**No retry in V2**" clause and
a "Discord push failure is fatal" requirement. Bolting retry on is NOT a pure ADD — it directly
contradicts that clause. Treated it exactly like v3-llm-throttle did on the summarizer side:
- 1 ADDED requirement carrying the retry mechanics (classification + backoff + Retry-After).
- 2 MODIFIED requirements (plain-text "fatal" + embed "fatal") whose trigger is re-worded from
  "any POST failure" to "a failure **not recovered by retry**", and BR-001-001 explicitly says it
  SUPERSEDES the no-retry clause of BR-V2-005-004 while preserving every other guarantee
  (exit 1, no stacktrace, URL-never-leaked, no rollback).
A pure ADD would have left two contradictory specs (fail-now vs retry-then-fail). Rule of thumb:
if a change flips a behavior an existing requirement explicitly froze, it's MODIFIED, not ADDED —
grep the living spec for the exact clause you're overturning and cite it in the new BR.

Two more traps this "just add retry" ask hid:
- **Transient/non-transient must be a CLOSED set, spec'd in a BR.** Reused conventions.md's
  GitHub policy (4xx=permanent-caller, 5xx/429=retryable) for the OUTBOUND Discord POST:
  transient = {429, 5xx, TimeoutException, RequestError}; non-transient = any other non-2xx
  (4xx except 429). 429 is the odd one — it's a 4xx but IS transient; call it out explicitly or
  dev lumps it with 403.
- **Retry-After is untrusted response data.** Spec it as: numeric → `max(Retry-After, backoff)`;
  missing/empty/non-numeric → ignore and fall back to pure backoff, never crash. Same
  "guard-don't-assume-shape" discipline as any external field.

Also **re-hit the delivery-6 first-comma-SHALL openspec-validate trap on a MODIFIED requirement**:
the modified embed req opened with `A POST failure ... (a long parenthetical with commas) SHALL
raise` — validate fails ("must contain SHALL or MUST") because the parser only scans up to the
first comma for the normative keyword. Fix: put SHALL in the first clause before any comma
(`An embed-mode POST failure that is not recovered by retry SHALL raise ...`), then move the
qualifying detail into a following sentence. Applies to MODIFIED reqs too, not just ADDED.

Injected `sleep: Callable = time.sleep` is a testability seam (assert wait values without real
delays) — pair every backoff AC with an injected fake sleep + a small max_retries so the suite
stays fast; and warn the dev that the existing parametrized `[400,401,404,429,500,503]` "expect
immediate DeliveryError" test now splits into transient(retry-then-error) vs non-transient(immediate).
