# Design — state-store-3 (S3 State Store)

> Feature: V1 JSON-file State Store for OSS Pulse. CLI tool, no HTTP API, no DB.
> Implements the existing `osspulse.ports.StateStore` Protocol + adapter dedup helpers.

---

## Sketch — Gap Analysis

**No critical gaps found.** The spec was SPEC-LOCKed (spec-auditor PASS, 0 blockers).

Analyzed 18 ACs (AC-3-001 … AC-3-018), 8 BRs, 2 INTs across 8 requirements.
Proposed: **0 HTTP endpoints** (CLI tool, no inbound API), **0 DB tables** (state is a
single JSON file), **3 source modules touched**, **3 key flows** (load / mark_seen+save /
corrupt-load).

Minor items (documented as assumptions / ADRs, no S2 return needed):
- **openapi.yaml does not apply** — no inbound HTTP API. Waived via ADR-004 citing R5 +
  cross-spec precedent ADR-007 (github-collector-2).
- **`Config.state_path` needs a default** so the two existing `Config(...)` call-sites
  (`config.py:106`, `tests/test_models.py:23`) keep working — confirmed safe (frozen
  dataclass, keyword construction).

---

## Architecture Overview

**Style**: Linear pipeline + ports/adapters (hexagonal-lite), per `context/architecture.md`.
The State Store is the **S3 adapter** sitting behind the `StateStore` port. It is pure
filesystem I/O — no GitHub, no LLM, no network (AC-3-017, BR-3-008).

```
pipeline (S7, future)            ports.StateStore (Protocol, UNCHANGED)
      │ holds concrete ref            load() -> dict
      ▼                               save(state: dict) -> None
JsonFileStateStore  ──implements──────────┘
  (src/osspulse/state/json_store.py)
      │ uses                         ┌─ adapter-only helpers (NOT on Protocol):
      ├─ models.RawItem (frozen)     │    is_seen(repo, item_type, item_id) -> bool
      ├─ state/errors.StateError ────┘    mark_seen(items: list[RawItem]) -> None
      └─ stdlib: json, os, tempfile, pathlib, datetime
```

**Cross-spec dependencies** (from `openspec/_cross-spec-context.md`):
- `osspulse.models.RawItem` (frozen, 7 str fields) — input to `mark_seen`; `body`/`url`/
  `title`/`item_id` may be empty strings (never assume non-null) — constraint from
  github-collector-2.
- `osspulse.ports.StateStore` Protocol — implemented unchanged (no new methods added to it).
- `osspulse.config.Config` (frozen dataclass) — gains a `state_path` field.

**Layer boundaries**: the adapter depends on core models + stdlib only; it never imports
the collector, summarizer, or any other adapter (anti-pattern guard in architecture.md).

---

## ADR-001: Keep `is_seen`/`mark_seen` on the adapter, not the `StateStore` Protocol

**Context**: The pipeline needs ergonomic dedup (`is_seen`, `mark_seen`). The existing
`StateStore` Protocol is `load() -> dict` / `save(state) -> None`. Should the helpers be
promoted to the Protocol? (Handoff §2 WATCH; AC-3-018 requires the Protocol stay
unchanged in V1.)

**Options**:

| Option | Pros | Cons |
|--------|------|------|
| A. Helpers on concrete `JsonFileStateStore` only; Protocol unchanged | Zero blast radius; honors AC-3-018 + github-collector-2 ADR-001 (port signature untouched); dict stays the serialization contract | Pipeline must hold a concrete type (or a wider protocol) to call helpers |
| B. Add `is_seen`/`mark_seen` to the `StateStore` Protocol | One interface for all callers | Violates AC-3-018 (V1 must not alter Protocol); widens a shared interface no other store implements yet; speculative for a single V1 impl |

**Decision**: **Option A.** AC-3-018 explicitly forbids altering the Protocol in V1, and
github-collector-2 ADR-001 set the precedent that port signatures stay untouched when a
single adapter needs richer behavior. The pipeline (S7, future) references the concrete
`JsonFileStateStore` for dedup; any code that only persists uses the `StateStore` Protocol.

**Consequences**: A future change can introduce a `SeenStore` Protocol (or extend
`StateStore`) once a second implementation (e.g. SQLite) actually exists — deferred, not
speculative. `load`/`save` remain the stable serialization seam.

## ADR-002: Atomic write via `tempfile` in `state_path.parent` + `os.replace`

**Context**: AC-3-007/AC-3-008 require crash-safe writes. `os.replace` is atomic only
**within the same filesystem** (handoff §4 risk). A temp file in `/tmp` could be on a
different mount, breaking atomicity.

**Options**:

| Option | Pros | Cons |
|--------|------|------|
| A. Temp file in `state_path.parent`, then `os.replace(tmp, state_path)` | Same dir ⇒ same filesystem ⇒ guaranteed atomic rename; standard pattern | Must ensure parent dir exists first (already needed by AC-3-015) |
| B. `tempfile.mkstemp()` (system temp) then `shutil.move` | Simple | System temp may be a different fs → `move` falls back to copy+delete = NOT atomic; reintroduces RF-1 |
| C. Write in place, `fsync`, hope | Trivial | Crash mid-write = truncated/corrupt file — violates AC-3-008 |

**Decision**: **Option A.** Create the temp file in the target's parent directory
(`tempfile.NamedTemporaryFile(dir=state_path.parent, delete=False)` or `mkstemp(dir=...)`),
write + flush + `os.fsync`, then `os.replace`. Clean up the temp file on any write error.

**Consequences**: Parent dir must be created before writing (dovetails with AC-3-015).
Atomicity holds on all POSIX + Windows same-volume cases. A leftover temp file after a
hard crash is harmless (ignored on next run; could be swept later — out of scope V1).

## ADR-003: `StateError` lives in `src/osspulse/state/errors.py`

**Context**: AC-3-009/010/016 require a clear `StateError` for corrupt/unwritable state.
Where does the exception class live? `config.py` already defines `ConfigError(Exception)`
as a module-local error (precedent).

**Options**:

| Option | Pros | Cons |
|--------|------|------|
| A. `state/errors.py` → `class StateError(Exception)` | Mirrors `ConfigError` precedent (per-module error); keeps `state` package self-contained; importable without circular deps | One extra small module |
| B. Put `StateError` in `models.py` | Central | `models.py` is pure data (frozen dataclasses, no behavior/errors) — pollutes the data layer; architecture.md says core models have no I/O concerns |
| C. Define inside `json_store.py` | Fewest files | Couples the error type to one adapter; a future SQLite store would import an adapter just for the error |

**Decision**: **Option A.** A dedicated `state/errors.py` matches the `ConfigError`
pattern, keeps the error reusable across future state adapters, and avoids polluting
`models.py`.

**Consequences**: `StateError` is raised by `JsonFileStateStore` and surfaces to the CLI
as `Error: <message>` exit 1 (conventions.md). The CLI layer (S7) maps it like `ConfigError`.

## ADR-004: No `openapi.yaml` for this CLI-only change (R5 waiver)

**Context**: R5 mandates a separate `openapi.yaml`. This change exposes **no inbound HTTP
API** (OSS Pulse is a CLI tool; the State Store is an internal adapter).

**Options**:

| Option | Pros | Cons |
|--------|------|------|
| A. Skip openapi.yaml; document the internal contract in §API Design | Honest — there is no HTTP surface; matches github-collector-2 ADR-007 precedent | Formal deviation from R5 (justified here) |
| B. Emit a stub openapi.yaml stating "no HTTP API" | Literal R5 compliance | A contentless file; misleading; the foundation change did this only because its agent read R5 literally — superseded by ADR-007 |

**Decision**: **Option A**, citing R5 + cross-spec precedent **ADR-007** (github-collector-2:
"no openapi.yaml when change has no inbound HTTP API"). The internal stage contract is the
`StateStore` Protocol + the JSON document shape, fully specified in §API Design / §DB Schema.

**Consequences**: cross-artifact-audit will not expect an openapi.yaml for this change.
tasks.md and design.md cover the contract instead.

---

## API Design

No HTTP API (ADR-004). The "API" is the internal contract:

**Port (unchanged) — `osspulse.ports.StateStore`**
```python
class StateStore(Protocol):
    def load(self) -> dict: ...
    def save(self, state: dict) -> None: ...
```

**Concrete adapter — `osspulse.state.json_store.JsonFileStateStore`**
```python
class JsonFileStateStore:                      # implements StateStore (structural)
    def __init__(self, state_path: str | Path) -> None: ...
    def load(self) -> dict: ...                # AC-3-001, AC-3-002, AC-3-009..012
    def save(self, state: dict) -> None: ...   # AC-3-001, AC-3-007, AC-3-013..016
    def is_seen(self, repo: str, item_type: str, item_id: str) -> bool: ...   # AC-3-003, AC-3-005
    def mark_seen(self, items: list[RawItem]) -> None: ...                    # AC-3-003..006
```

**Identity key helper (internal, pure)**
```python
def _identity_key(item_type: str, item_id: str) -> str:
    return f"{item_type}:{item_id}"     # repo is the outer dict key (AC-3-005)
```

**`Config` field added** (`osspulse.models.Config`):
```python
state_path: str = "./.osspulse/state.json"   # AC-3-013; default keeps existing call-sites valid
```
`load_config` reads optional `state_path` from the TOML `[state]` section (or top-level),
defaulting to `./.osspulse/state.json`.

**Behavioral contract of the helpers**
- `is_seen(repo, item_type, item_id)` → reads in-memory loaded state (lazy-loaded once),
  returns `True` iff `state["seen"][repo]["{item_type}:{item_id}"]` exists.
- `mark_seen(items)` → for each `RawItem`, if not already present, set
  `seen[item.repo]["{item.item_type}:{item.item_id}"] = now_utc_z()`; never overwrite an
  existing value (AC-3-004); then persist atomically. Empty list = no-op save-safe (AC-3-006).

---

## DB Schema

No database (V1 is a JSON file; PROJECT_SPEC §7). The **persisted document** (locked at S2):

```json
{
  "version": 1,
  "seen": {
    "facebook/react": {
      "issue:12345": "2026-06-24T13:05:00Z",
      "issue:12346": "2026-06-24T13:05:01Z"
    },
    "vercel/next.js": {
      "issue:987": "2026-06-23T09:00:00Z"
    }
  }
}
```

- `version`: integer, `1` in V1 (AC-3-014). Unknown/newer → `StateError` (AC-3-010).
- `seen`: object keyed by `repo` → object keyed by `"{item_type}:{item_id}"` →
  `first_seen_at` (UTC ISO-8601 with trailing `Z`, AC-3-003).
- Missing `seen` key OR 0-byte file → treated as empty `{}` (AC-3-011, AC-3-012).
- Encoding: UTF-8 (A-A2).

**In-memory representation**: a plain `dict` (the Protocol's contract). The adapter does NOT
introduce a typed dataclass for state in V1 — `load`/`save` round-trip a dict (AC-3-001),
keeping the serialization seam simple and matching the Protocol return type.

---

## Error Mapping

| Condition | Raised | Surfaced to user (via CLI/S7) | AC |
|-----------|--------|-------------------------------|-----|
| Malformed JSON on load | `StateError` | `Error: state file is corrupt: <detail>` exit 1 | AC-3-009 |
| Unknown/newer `version` | `StateError` | `Error: unsupported state version <n> (expected 1)` exit 1 | AC-3-010 |
| Parent dir/file not writable | `StateError` | `Error: cannot write state to <path>: <reason>` exit 1 | AC-3-016 |
| 0-byte file | — (tolerated) | empty state, no error | AC-3-011 |
| Missing `seen` key | — (tolerated) | empty state, no error | AC-3-012 |
| Missing file on load | — (tolerated) | empty state, no error | AC-3-002 |

`StateError` message MUST NOT leak file contents beyond a short reason. Surfacing format
mirrors `ConfigError` (`Error: <message>`, exit 1) per conventions.md. No raw traceback for
these handled errors.

---

## Sequence Flows

**Flow 1 — load (cold)**
```
caller.load()
  → path exists?  no → return {"version":1,"seen":{}}            (AC-3-002)
                  yes → read bytes
       → 0 bytes? → return empty state                            (AC-3-011)
       → json.loads → JSONDecodeError? → raise StateError         (AC-3-009)
       → version unknown? → raise StateError                      (AC-3-010)
       → missing "seen"? → treat as {}                            (AC-3-012)
       → return dict
```

**Flow 2 — mark_seen + atomic save**
```
caller.mark_seen(items)
  → state = self._loaded_state (lazy load once)
  → items empty? → still safe; loop adds nothing                  (AC-3-006)
  → for item in items:
        key = f"{item.item_type}:{item.item_id}"                  (AC-3-005, empty id ok)
        bucket = state["seen"].setdefault(item.repo, {})
        if key not in bucket: bucket[key] = now_utc_z()           (AC-3-004 no overwrite)
  → save(state)
        mkdir -p state_path.parent                                (AC-3-015)
        tmp = NamedTemporaryFile(dir=state_path.parent, delete=False)
        write json + flush + os.fsync ; close
        os.replace(tmp, state_path)                               (AC-3-007 atomic)
        on error: unlink tmp, raise StateError                    (AC-3-016)
```

**Flow 3 — crash mid-save**
```
process killed between write(tmp) and os.replace
  → state_path still points at the OLD valid file                (AC-3-008)
  → tmp file orphaned (harmless, ignored next run)
```

---

## Edge Cases

All 16 proposal ECs map to ACs/flows above. Design-level notes on the tricky ones (handoff §4):

- **EC-002 / empty `item_id`**: key becomes `"issue:"` — a valid, stable dict key. No crash;
  `is_seen` round-trips it. (AC-3-005)
- **EC-007/EC-008 / crash & overlap**: atomic replace ⇒ last-writer-wins, never corrupt
  (ADR-002). No locking (A-A3, out of scope).
- **EC-009..012 / corrupt-vs-empty boundary**: the precise rule is in §Sequence Flow 1 —
  *parse failure or bad version = loud*; *absent/empty/partial-shape = empty*. This is the
  hardest edge; it is fully enumerated, not left to dev judgment.
- **EC-013 / missing parent dir**: created on save (AC-3-015), before the temp file is opened
  there (ordering matters — mkdir first, else NamedTemporaryFile(dir=...) fails).

---

## Performance

- State file is small (identity key + 20-char timestamp per item). 10k items ≈ a few hundred
  KB — `json.load`/`json.dumps` is O(n) and sub-millisecond at this scale (EC-003).
- `load` is done **once per run** (lazy, cached in the adapter instance); `save` once after
  `mark_seen`. No per-item file I/O.
- `os.fsync` adds one sync per save — negligible for a once-per-run CLI; worth the
  crash-safety guarantee.
- No indexing/DB needed at V1 scale; SQLite is the V2 escape hatch (version field).

---

## Security

STRIDE not triggered (no auth/PII/token/network surface — proposal Early Risk Flags). Local
file risks addressed:
- **RF-1 (Tampering/integrity)** → atomic write (ADR-002, AC-3-007/008).
- **RF-2 (silent reset)** → fail loud on corrupt/bad-version; never auto-reset (AC-3-009/010).
- **RF-3 (path handling)** → `state_path` is operator config, not untrusted network input; no
  SSRF/path-injection vector. Parent dir created with default umask; no privilege change. The
  store writes only under the configured path.
- No secrets touch this module (token/LLM key live in config/collector only). State file
  contains only public issue identities + timestamps — no sensitive data.

---

## Risk Assessment

- [Risk: `os.replace` non-atomic across filesystems] → Mitigation: temp file in
  `state_path.parent` (ADR-002); same volume guaranteed.
- [Risk: corrupt-vs-empty misclassification re-processes or loses history] → Mitigation:
  explicit boundary in Sequence Flow 1 + dedicated ACs (AC-3-009/011/012) + tests for each.
- [Risk: empty `item_id` produces colliding/odd keys] → Mitigation: keys are namespaced by
  `item_type` and bucketed by `repo`; empty id yields `"issue:"`, still unique per repo+type.
- [Risk: `Config` field addition breaks call-sites] → Mitigation: `state_path` has a default;
  verified only 2 keyword call-sites exist.
- [Risk: future V2 needs a different key/shape] → Mitigation: `version` field gates migration;
  AC-3-005 stays [ASSUMED] until V2 is specified (do not design for it now).

---

## Implementation Guide

**Recommended order** (data/schema → adapter logic → config wiring → tests):
1. `src/osspulse/state/errors.py` — `class StateError(Exception)` (ADR-003).
2. `src/osspulse/models.py` — add `state_path: str = "./.osspulse/state.json"` to `Config`.
3. `src/osspulse/config.py` — read optional `state_path` in `load_config` (default applies).
4. `src/osspulse/state/json_store.py` — `JsonFileStateStore`: `_identity_key`, `now_utc_z`,
   `load`, `save` (atomic), `is_seen`, `mark_seen`.
5. Tests last (per R10) — `tests/test_state_store.py` covering every AC + corrupt-vs-empty.

**Patterns to follow** (with file paths):
- Error class mirrors `ConfigError` in `src/osspulse/config.py:18`.
- Atomic write: `tempfile.NamedTemporaryFile(dir=Path(state_path).parent, delete=False)` →
  write → `flush()` → `os.fsync(fileno)` → close → `os.replace(tmp_name, state_path)`; on
  exception `os.unlink(tmp_name)` then `raise StateError(...)`.
- UTC timestamp: `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` (Z-suffix, matches
  `RawItem.created_at` form).
- Structural typing: `JsonFileStateStore` need not subclass `StateStore` (it's a `Protocol`);
  just match `load`/`save` signatures (same approach as `GitHubCollector` vs `GitHubClient`).
- Tests: use `tmp_path` fixture (pytest) for the state file — never write to the real FS
  (stack.md). For the unwritable-path case, use `tmp_path` with `chmod` or a path under a
  read-only dir; skip on platforms where chmod is a no-op.

**Gotchas**:
- `mkdir(parents=True, exist_ok=True)` on `state_path.parent` MUST run before opening the temp
  file in that dir (else `NamedTemporaryFile(dir=...)` raises) — AC-3-015.
- Distinguish `json.JSONDecodeError` (→ `StateError`, AC-3-009) from an empty file (→ empty
  state, AC-3-011): check `if not raw.strip(): return empty` BEFORE `json.loads`.
- `isinstance(version, bool)` is `True` for `int` — guard `version` type if strictness needed
  (mirror the bool-trap note already in `config.py:_validate_lookback`).
- Never overwrite `first_seen_at` on re-mark (AC-3-004) — use `if key not in bucket`.
- Empty `item_id` is valid input (AC-3-005 / EC-002) — do not validate/reject it here.
