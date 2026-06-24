---
name: qa-analysis
description: >
  QA Analysis — Risk scanning + Spec-TC gap review trong 1 session.
  Gộp SA2 (Risk Scout + Bug Hunter) + SA10 (Spec-TC Gap Reviewer).
  Gọi sau khi S2 done, trước hoặc song song S3. Output vào openspec/changes/<change>/qa/
---

# QA Analysis — Risk Scan + Spec-TC Gap Review

Gộp 2 phases: (1) Risk scanning từ spec, (2) Spec-TC gap review.
Chạy trong 1 session để tiết kiệm context load.

## Khi nào dùng

- Sau S2 (AC confirmed) — quét risk trước khi design
- Sau khi có test cases — review gaps giữa spec và TC
- QA agent gọi khi chạy `/s5` pipeline

## Input

1. `openspec/changes/<change>/proposal.md` + spec deltas — đọc `_Structured Extract` trước
2. `docs/knowledge/{ticket}/` — nếu tồn tại
3. `docs/knowledge/_shared/lesson-learned.md` — bug patterns đã biết
4. `dev-test-report.md` — nếu có (cho gap review)

## Phase 1 — Risk Scanning

### Bước 1: Map feature

```
1. Đọc _Structured Extract → AC list, business rules, integration points
2. Đọc lesson-learned.md → có pattern bug quen nào cho domain này?
3. Liệt kê: actors, actions, states, integration points
```

### Bước 2: Quét risk theo 8 chiều

**3.1 Edge Cases** — Ranh giới dữ liệu:
- Số: min, max, âm, 0, thập phân, rất lớn
- String: rỗng, khoảng trắng, ký tự đặc biệt, injection, unicode, quá dài
- Date: quá khứ, tương lai, múi giờ, ngày đặc biệt
- List: rỗng, 1 phần tử, rất lớn
- Optional: không truyền vs null vs rỗng

**3.2 Logic Conflicts** — Mâu thuẫn business rules:
- Rule A + Rule B đồng thời?
- Thứ tự bước quan trọng?
- Dead state không có rule xử lý?

**3.3 Missing Error Handling**:
- External service timeout/fail?
- DB record không tồn tại / đã xóa / đang lock?
- Network mất giữa chừng?
- Concurrency: 2 request cùng modify 1 record?

**3.4 Permission & Data Isolation**:
- User A xem/sửa data User B?
- API gọi trực tiếp không qua auth?
- Token/session hết hạn giữa flow?

**3.5 Security (OWASP)**:
- Input validation server side? SQLi? XSS? IDOR?
- Rate limiting? Sensitive data exposure?

**3.6 Integration & Side Effects**:
- Event/webhook trigger? Consumer fail?
- Cache invalidation? Notification duplicate?

**3.7 UX Failures**:
- Double-click submit? Back browser? 2 tab? Idle quá lâu?

**3.8 High-Impact Bug Patterns**:
- Double Submit / Replay (thiếu idempotency key)
- Race Condition (nhiều user claim 1 resource)
- State Mismatch After Failure (thiếu rollback)
- Stale Data (cache không invalidate)

### Bước 3: Output risk report

Lưu: `openspec/changes/<change>/qa/risk_analysis.md`

```markdown
# Risk Analysis — {ticket-id}
Date: {date}

## Summary
- Total: X risks (🔴 Critical: X | 🟠 High: X | 🟡 Medium: X | 🟢 Low: X)

## Risk List

[R-001] 🔴 {Tên ngắn}
  Chiều: {Edge Case / Logic / Error / Permission / Security / Integration / UX}
  AC liên quan: AC-{ticket}-{NNN}
  Mô tả: {kịch bản cụ thể}
  Hệ quả: {bug / data sai / security}
  Đề xuất: {Dev handle / AC bổ sung}
  Test focus: {test case cần thêm}

[R-002] ...
```

## Phase 2 — Spec-TC Gap Review

Chạy SAU khi có test cases (từ dev-test-report.md hoặc QA test scenarios).

### Bước 1: Extract AC list

Đọc `_Structured Extract` → lấy tất cả AC-IDs.
- Bỏ qua: `[ASSUMED]`, `[UNCLEAR]` — chưa confirmed
- Phân tích đầy đủ: `[CONFIRMED]` và còn lại

### Bước 2: Build TC coverage map

Đọc theo thứ tự:
1. `dev-test-report.md` → AC coverage từ Dev
2. QA test scenarios (nếu đã generate)
3. Build: `{AC-ID → [test files/IDs] hoặc []}`

### Bước 3: Check source code (nếu có access)

Với mỗi AC confirmed:
```
1. Extract 2-3 keywords từ AC description
2. Grep source code: controllers/, services/, modules/
3. Kết luận: FOUND / NOT_FOUND / UNCERTAIN
```

### Bước 4: Classify gaps

```
BOTH_MISS  : Không có TC + không có code → NGUY HIỂM NHẤT
TC_MISS    : Không có TC, code có thể có → QC gap
DEV_MISS   : Có TC, không tìm thấy code → Dev gap
SHALLOW_TC : TC có nhưng assertion quá yếu (chỉ toBeVisible, không check value)
OK         : Có TC + có code
```

### Bước 5: Gate decision

```
🚫 BLOCK: Bất kỳ BOTH_MISS | TC_MISS trên P1 AC | P1 coverage < 100%
⚠️ WARNING: TC_MISS trên P2 (≤3) | SHALLOW_TC trên P1 | DEV_MISS
✅ PASS: 0 BOTH_MISS + 0 TC_MISS P1 + P1 coverage 100%
```

### Output gap report

Lưu: `openspec/changes/<change>/qa/spec_tc_gap_report.md`

```markdown
# Spec-TC Gap Report — {ticket-id}
Date: {date}
Mode: Full (Spec+TC+Code) | Spec-TC Only

## Gap Summary
| Type | Total | P1 | P2 |
|------|-------|----|----|
| BOTH_MISS | X | X | X |
| TC_MISS | X | X | X |
| DEV_MISS | X | X | X |
| SHALLOW_TC | X | X | X |
| OK | X | X | X |

AC Coverage: X/X (X%) — P1: X% | P2: X%

## Actions Required
- Thêm TC cho: {AC-IDs}
- Dev implement: {AC-IDs}
- Strengthen assertions: {TC-IDs}

## Gate: PASS / WARNING / BLOCK
```

## Output tổng hợp

```
[qa-analysis] Completed:
- Risk scan: X risks (Critical: X, High: X)
- Gap review: {PASS/WARNING/BLOCK} — AC coverage X%
- Files:
  - openspec/changes/<change>/qa/risk_analysis.md
  - openspec/changes/<change>/qa/spec_tc_gap_report.md
```