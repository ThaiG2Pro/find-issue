---
name: qa-execution
description: >
  QA Execution — Test runner + bug reporting + RCA + regression scope.
  Gộp SA7 (Test Runner) + SA5 (RCA) + SA4 (Regression Scope).
  Chạy tests, report bugs lên Redmine, phân tích root cause, xác định retest/regression scope.
---

# QA Execution — Run Tests + Report Bugs + RCA + Regression

3 capabilities trong 1 skill: (1) Run tests + report, (2) RCA cho bugs C/H, (3) Regression/retest scope.

## Khi nào dùng

- Sau qa-test-design PASS/WARNING — chạy tests
- Khi phát hiện bug Critical/High — RCA
- Sau bug fix — retest scope
- Trước release — regression scope

## Input

1. Playwright scripts từ qa-test-design
2. `openspec/changes/<change>/qa/coverage_summary.md`
3. Redmine access (MCP) — cho bug posting + milestone reading
4. Ticket ID (parse từ spec folder name)

## Phase 1 — Test Runner + Bug Reporter

### Prerequisites (gate cứng)

- [ ] Playwright scripts sẵn sàng (không còn TODO selectors)
- [ ] Test data ready (synthetic, không production data)
- [ ] Environment accessible (STG/UAT)
- [ ] Ticket ID có (parse từ spec folder: `{ticket_id}-{slug}`)

### Chạy tests

```bash
npx playwright test tests/e2e/{feature}/ --reporter=list,html
```

Phân loại kết quả:
- PASS → không xử lý
- FAIL → tạo bug report + post Redmine
- SKIP → ghi nhận
- FLAKY (fail lần 1, pass retry) → ghi flaky log, không tạo bug

### Bug report format

Lưu: `openspec/changes/<change>/qa/bugs/{BUG_ID}/report.md`

```markdown
# {BUG_ID} — {Tên bug ngắn}

| Field | Value |
|-------|-------|
| Bug ID | {PREFIX}-BUG-{NNN} |
| Test ID | {TC-ID} |
| AC | AC-{ticket}-{NNN} |
| Loại | UI / Function / Performance / Security |
| Severity | Critical / High / Medium / Low |
| Môi trường | {STG/UAT} |

## Steps to Reproduce
1. {step}

## Expected Result
{từ test case Expected Result}

## Actual Result
{mô tả chính xác + error message nếu có}
```

### Post Redmine

Subject: `[{Env}][{Loại}] {Tên bug}`

```
1. Dùng MCP mcp_redmine_redmine_request để tìm parent story trong Milestone
2. Post bug issue với parent_issue_id = story (KHÔNG post vào Milestone trực tiếp)
3. Attach screenshots nếu có
```

Duplicate detection: query open bugs trước khi post.
- Trùng rõ (≥2/3 match) → DỪNG, báo duplicate
- Có thể trùng → tạo mới, note "Possible duplicate: #ID"

### Quality Sign-off

Lưu: `openspec/changes/<change>/qa/quality_signoff.md`

```markdown
# Quality Sign-off — {ticket-id}

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| Critical/High bugs open | 0 | X | ✅/❌ |
| AC Coverage | 100% | X% | ✅/❌ |
| Mutation Score | ≥80% | X% | ✅/❌ |

Decision: **GO / NO-GO**
```

## Phase 2 — RCA (Root Cause Analysis)

Trigger: Bug Critical hoặc High được phát hiện.

### Input

- Bug report (steps, expected vs actual)
- Error logs / stack trace (paste hoặc path → auto-read)
- Functional Spec + AC
- Design docs (OpenAPI, DB schema)

### Phân tích 3 chiều

**Chiều 1 — Tầng lỗi**:
- Frontend: render, state management, validate
- Backend: API sai data/status, business logic, error handling
- Data: query sai, schema, migration
- Integration: external service format/timeout

**Chiều 2 — Nguồn gốc SDLC**:
- Code bug (S4): implement sai spec → fix cost 15×
- Design bug (S3): API/DB design thiếu → redesign cost 20×
- Spec bug (S2): AC thiếu/mâu thuẫn → re-spec cost 25×

**Chiều 3 — Reproduce**:
- Stable → confidence cao
- Intermittent → có thể race condition → cần thêm logs
- Không reproduce → chưa kết luận

### Output

Lưu: `openspec/changes/<change>/qa/rca/{BUG_ID}_rca.md`

```markdown
# RCA — {BUG_ID}

## Bug Summary
Bug ID / TC ID / Severity / Layer

## Root Cause
Hypothesis: {mô tả} — Confidence: Cao/Trung bình/Thấp
Evidence: {1, 2, 3}

## Loop Recommendation
→ Loop về: S4 / S3 / S2
→ Action: Dev cần [...] | BA cần [...] | QC cần [...]
```

## Phase 3 — Regression & Retest Scope

### Mode 1 — Retest (per bug fix, <30 phút)

Trigger: Dev fix xong 1 bug → cần verify.

```
1. Đọc bug fix ticket → xác định fix type + files changed
2. Map với test cases → lấy TC gốc (verify fix) + TC direct impact
3. KHÔNG mở rộng indirect impact — scope nhỏ, nhanh
```

Output: `openspec/changes/<change>/qa/retest_scope.md`
```
Bug: {BUG_ID} | Fix type: {type}
TC verify fix: {TC-ID}
TC direct impact: {list} ({X} TCs, ~{X} phút)
```

### Mode 2 — Regression (per milestone, trước release)

Trigger: Phần lớn bugs trong Milestone đã Resolved.

```
1. Dùng MCP Redmine đọc Milestone → liệt kê stories + bugs fixed
2. Phân tích modules bị ảnh hưởng
3. Module bị ảnh hưởng: TC verify fix + ALL P1 + ALL P2
4. Module không bị chạm: P1 smoke only
5. Deduplicate → regression suite
```

Output: `openspec/changes/<change>/qa/regression_scope.md`
```
Milestone: {name} | Bugs fixed: X | Modules affected: X
Total TCs: X (verify fix: X + P1/P2: X + smoke: X)
```

## Output tổng hợp

```
[qa-execution] Completed:
- Test results: PASS X | FAIL X | SKIP X | FLAKY X
- Bugs posted: {BUG-IDs} → Redmine #{IDs}
- RCA: {X} reports (loop recommendations: S4×X, S3×X)
- Sign-off: GO / NO-GO
- Files:
  - openspec/changes/<change>/qa/quality_signoff.md
  - openspec/changes/<change>/qa/bugs/*/report.md
  - openspec/changes/<change>/qa/rca/*_rca.md
```