# Sprint Retro: delivery-6

*Ngày: 2026-06-30 · Branch: `feature/6-delivery` · Base: `feature/5-digest-renderer`*

## Sprint Health Score: 91/100

| Dimension | Score | Ghi chú |
|-----------|-------|---------|
| Gate compliance | 25/25 | 5/5 gates pass, 0 violations |
| AI performance | 23/25 | 2 deviations minor, cả hai justified |
| Rework cost | 25/25 | 0 loop-back |
| Delivery quality | 18/25 | 1 accepted gap (BrokenPipe/DeliveryError CLI handler chưa unit test riêng); coverage 98.14% |

---

## Gate Compliance: 5/5 ✅

| Gate | Output mong đợi | Kết quả | Ghi chú |
|------|-----------------|---------|---------|
| S1 → S2 | Requirement pack + ACs | ✅ | 3 stories, 14 edge cases, scope closed |
| 🔒 S2 SPEC LOCK | spec-auditor PASS + validate --strict | ✅ | 20 ACs (16 CONFIRMED, 4 ASSUMED), 0 MISSING/UNCLEAR |
| 🔍 S3 DESIGN REVIEW | cross-artifact-audit 0 CRITICAL | ✅ | 6 ADRs, sketch=no critical gaps |
| S4 → S5 | Tests pass + coverage ≥ 80% | ✅ | 245/245, 98.14% |
| S5 → S6 | QA GO + 0 Critical bugs | ✅ | 20/20 ACs, 0 bugs |

Không có loop-back. Không có gate violation.

---

## AI Performance

| Metric | Target | Actual |
|--------|--------|--------|
| AI-detectable bugs caught by AI | ≥ 90% | ~100% ✅ |
| Logic bugs missed by AI | 0 | 0 ✅ |
| Spec adherence (no unauthorized deviation) | 100% | 98% ✅ |
| Test coverage on new code | ≥ 80% | 98.14% ✅ |
| Gates fired correctly | ✅ | ✅ |

2 minor deviations tại S4, cả hai justified và logged trong `_decisions.jsonl`:
- `task-1.1`: xóa `Digest` import thừa trong `ports.py` (ruff F401 — đúng).
- `task-7.1-cli-test`: update stub assertion trong `test_cli.py` (test implementation detail, không phải AC).

---

## 4Ls

### Liked ✅
- D-1 (stale port stub `send(Digest)` → `deliver(str)`) được flag sớm ở S2 — không trôi đến S4.
- ADR-002 tái dùng atomic-write pattern từ `state-store-3` — không reinvent, có test ngay lập tức.
- Coverage 98.14% — toàn bộ branch condition được test, kể cả `StdoutDelivery` injectable stream.
- 0 MISSING/UNCLEAR trong spec — không có ambiguity trôi qua S2.

### Learned 📖
- Port stub viết trước upstream sẽ drift về type. Cần diff port signature vs return type thực của producing stage — không tin stub cũ.
- `BrokenPipeError` bắt trong adapter không đủ: interpreter còn một final flush sau khi `deliver()` return. Chỉ `os.dup2(devnull, fileno()) + Exit(0)` ở CLI top-level mới suppress sạch.

### Lacked 🔧
- `memory/architect.md` chưa tồn tại trước retro này — ADR pattern reuse chưa có chỗ persist cho architect agent. → Đã tạo trong retro này.
- Subagent spawn (`InvokeSubagents`) bị `invalid_redirect_uri` trong session — phải chạy S4/S5/S6 trực tiếp.

### Longed For 💡
- Checklist tự động diff "port stub type" vs "upstream producing stage return type" ở cổng S2→S3.
- `memory/architect.md` pattern library cho ADR trade-offs tái dùng. → Đã khởi tạo.

---

## Action Items

| # | Item | Owner | Status |
|---|------|-------|--------|
| 1 | Tạo `memory/architect.md` | sdlc-full | ✅ Done — 2026-06-30 |
| 2 | Thêm diff port-type check vào S2 checklist của analyst | analyst | `[ ]` pending |
| 3 | Investigate subagent `invalid_redirect_uri` trong Kiro CLI | DevOps/setup | `[ ]` pending |

---

## Memory Harvest

| File | Hành động |
|------|-----------|
| `memory/analyst.md` | De-dup — lesson stale port stub đã có sẵn (ghi bởi analyst tại S2) |
| `memory/developer.md` | De-dup — BrokenPipeError + atomic write + subagent infra đã có sẵn (ghi bởi developer tại S4) |
| `memory/architect.md` | ✅ Tạo mới — 2 lessons: atomic-write pattern reuse + per-module error class pattern |
