---
name: qa-test-design
description: >
  QA Test Design — Test case generation + Playwright automation scripts + mutation gate.
  Gộp SA3 (Test Designer) + SA6 (Automation Writer) + SA8 (Mutation Gate).
  Chạy tuần tự trong 1 session. Output: Excel + scripts + gate decision.
---

# QA Test Design — Test Cases + Automation + Mutation Gate

3 phases trong 1 session: (1) Design test cases, (2) Write automation scripts, (3) Mutation effectiveness gate.

## Khi nào dùng

- Sau qa-analysis (risk scan done)
- QA agent gọi trong `/s5` pipeline (Standard/Full tier)
- Cần tạo test plan + automation cho feature mới

## Input

1. `openspec/changes/<change>/proposal.md` + spec deltas — `_Structured Extract` (AC list, business rules)
2. `openspec/changes/<change>/qa/risk_analysis.md` — risk list từ qa-analysis
3. `openspec/changes/<change>/design.md` — API/DB design
4. `openspec/changes/<change>/openapi.yaml` — API contracts
5. Source code (nếu có access) — cho selectors + mutation analysis

## Phase 1 — Test Case Design

### Bước 1: Phân tích feature

3 câu hỏi bắt buộc:
- Admin/CMS side có gì? → Form CRUD, list, filter, config
- Frontend/User-facing side có gì? → UI states, notifications
- Transaction/Exchange flow có gì? → Side effects, payments → P1 cao nhất

### Bước 2: Sinh test cases

Kỹ thuật:
| Kỹ thuật | Khi nào |
|----------|---------|
| [UC] Happy path | Mọi flow |
| [NEG] Invalid input | Mọi form/field |
| [BVA] Boundary | Field có giới hạn |
| [EP] Equivalence | Nhiều giá trị cùng behavior |
| [EG] Edge/Concurrency | Business rules đặc biệt |
| [SEC] Security | Mọi input field |

Priority: P1 = SEC + NEG core + UC happy + BVA + EG high risk. P2 = còn lại.

Automation level:
- Full Auto: input validation, happy path, security injection, API verification
- Partial: cần mock time/external service, có bước manual setup
- Manual: camera, QR, pixel-perfect visual, device-specific

### Bước 3: Format mỗi test case

```
Test ID: {PREFIX}-{NNN}
Technique: [UC/NEG/BVA/EP/EG/SEC]
Priority: P1/P2
Objective: [TECHNIQUE] Verify {action} → {expected}
Steps: numbered, 1 step per line
Expected: mỗi assertion bắt đầu bằng ✓, cụ thể, đo được
Requirement: AC-{ticket}-{NNN} (hoặc R-{NNN} cho risk items)
Automation: Full Auto / Partial / Manual
```

### Bước 4: Xuất test cases (format theo `_state.json.testcase_export`)

Format được **orchestrator chọn PER PIPELINE ở kickoff** và lưu sẵn — KHÔNG tự suy từ config/rigor ở
đây. Đọc `{CHANGE_DIR}/_state.json` → `testcase_export`:

| `testcase_export` | Output |
|-------------------|--------|
| `xlsx` | **`.xlsx`** — `openspec/changes/<change>/qa/testcases.xlsx` (báo cáo QA manager) |
| `md`   | markdown table — `openspec/changes/<change>/qa/testcases.md` |
| `none` | bỏ qua artifact test-case (không sinh file) |

> Nếu `_state.json` thiếu key `testcase_export` (state cũ): fallback `auto` → `full`→xlsx, `lite`→md,
> hotfix→none. Vẫn ưu tiên giá trị đã persist nếu có.

**Sinh `.xlsx`** — viết test cases ra `qa/testcases.json` (mảng object: `test_id, technique,
priority, objective, steps, expected, requirement, automation, status`) rồi chạy generator đã ship
cùng skill (python3, có sẵn trong shell của qa — KHÔNG cần Node):
```bash
python3 .kiro/skills/qa-test-design/gen_testcases_xlsx.py \
  openspec/changes/<change>/qa/testcases.json \
  openspec/changes/<change>/qa/testcases.xlsx
```
Cột chuẩn: `Test ID | Technique | Priority | Objective | Steps | Expected | Requirement | Automation | Status`.
Status được tô màu (Pass=green, Fail=red, N/A=grey) khi `openpyxl` có sẵn. **Thiếu `openpyxl`** →
generator tự fallback ghi `testcases.csv` (mở được bằng Excel) và in cảnh báo — KHÔNG fail gate.
File ghi vào `openspec/**` (trong write.allowedPaths của qa).

### Bước 5: Coverage summary

Lưu: `openspec/changes/<change>/qa/coverage_summary.md`

```markdown
## AC Coverage
| AC-ID | TC-IDs | Status |
|-------|--------|--------|
| AC-{id}-001 | TC-001, TC-002 | ✅ Covered |
| AC-{id}-005 | — | ❌ Not covered |

AC Coverage: X/X (X%)
Risk Coverage: X/X (X%)
```

Gate: AC P1 không covered → KHÔNG xuất, thêm TC trước.

## Phase 2 — Automation Script Writing

Chỉ chạy cho TC "Full Auto" + "Partial". Bỏ "Manual".

### Cấu trúc output

```
tests/e2e/{feature}/
├── {section-name}.spec.ts
├── pages/
│   └── {PageName}Page.ts
└── fixtures/test-data.ts
```

### Quy tắc viết

- TypeScript + Playwright Test + POM pattern
- Test name: `"[TC-ID] {Test Objective}"`
- Selectors ưu tiên: data-testid > role+name > placeholder > text > CSS
- Không tìm thấy selector → `[data-testid="TODO_replace_me"]` + comment
- Mỗi ✓ trong Expected Result = 1 assertion
- TC Partial: comment `// MANUAL STEP REQUIRED: {description}`
- Security tests: loop qua XSS_PAYLOADS array
- BVA tests: loop qua boundary cases array

### Gherkin (cho mỗi TC auto)

```gherkin
Scenario: {mô tả ngắn}
  Given {precondition}
  When {action}
  Then {assertion}
```

## Phase 3 — Mutation Effectiveness Gate

### Detect mode

```
Có source code + unit tests + Stryker config → Mode A: Full Mutation Testing
Có source code + unit tests, chưa config     → Mode A: Setup + chạy
Không có unit tests                           → Mode B: Assertion Quality Analysis (static)
```

### Mode A — Full Mutation Testing

```bash
npx stryker run  # JS/TS
# Parse: mutation score, survived mutants, killed count
```

Đối chiếu survived mutants ↔ test cases:
- Survived ở logic X → TC nào cover X? → assertion đủ kill mutant?
- Nếu không → Hollow TC

### Mode B — Assertion Quality Analysis (static)

Phát hiện Hollow TCs:
- [H1] Chỉ check tồn tại, không check giá trị
- [H2] Check UI nhưng bỏ qua business outcome
- [H3] Expected Result mơ hồ ("thành công", "đúng")
- [H4] BVA không assert tại đúng boundary
- [H5] Negative case không verify error message cụ thể

Sinh mutation scenarios (6 operators):
- MO-1: Boundary shift (300000 → 300001)
- MO-2: Operator swap (> → >=)
- MO-3: Off-by-one (value ± 1)
- MO-4: Condition removal (A && B → A)
- MO-5: Return value (calc() → 0)
- MO-6: Step skip

Build kill matrix → tính mutation score (estimated).

### Gate decision

```
Score ≥ 80% + 0 Hollow TC + AC coverage 100% → ✅ PASS
Score 60-79% HOẶC Hollow TC ≤ 3              → ⚠️ WARNING
Score < 60% HOẶC Hollow TC > 3               → 🚫 BLOCK → DỪNG
```

## Output tổng hợp

```
[qa-test-design] Completed:
- Test cases: X total (P1: X, P2: X)
- Automation: Full Auto X | Partial X | Manual X
- TODO selectors: X
- Mutation score: X% [actual/estimated]
- Hollow TCs: X
- Gate: PASS / WARNING / BLOCK
- Files:
  - openspec/changes/<change>/qa/coverage_summary.md
  - tests/e2e/{feature}/*.spec.ts
```