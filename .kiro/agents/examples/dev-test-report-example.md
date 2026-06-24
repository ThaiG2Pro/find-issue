---
name: dev-test-report-example
description: >
  Golden example of dev-test-report.md — S4 handoff artifact for QA. Contains: AC coverage table, test results, self-review log, design deviations, coverage report.
---

## Dev Test Report — 71000
Date: 2026-04-13

### Unit Test Coverage
| Module | Lines | Branches | Functions | Statements |
|--------|-------|----------|-----------|------------|
| brand.service | 92% | 85% | 100% | 91% |
| brand.controller | 88% | 80% | 100% | 87% |
| **Overall** | **91%** | **84%** | **100%** | **90%** |

### AC Coverage by Tests
| AC-ID | Test File | Test Name | Status |
|-------|-----------|-----------|--------|
| AC-71000-001 | brand.service.spec.ts | should return paginated list (AC-71000-001) | ✅ PASS |
| AC-71000-002 | brand.service.spec.ts | should apply pagination (AC-71000-002) | ✅ PASS |
| AC-71000-003 | brand.service.spec.ts | should search case-insensitive (AC-71000-003) | ✅ PASS |
| AC-71000-009 | brand.service.spec.ts | should create brand 201 (AC-71000-009) | ✅ PASS |
| AC-71000-011 | brand.service.spec.ts | should throw 409 duplicate (AC-71000-011) | ✅ PASS |
| AC-71000-021 | brand.service.spec.ts | should soft-delete 204 (AC-71000-021) | ✅ PASS |
| AC-71000-023 | — | — | ❌ NOT COVERED |
| AC-71000-026 | — | — | ❌ NOT COVERED |

### Integration Test Results
| Endpoint | Method | Test | Status |
|----------|--------|------|--------|
| internal/v1/brands | GET | paginated list | ✅ PASS |
| internal/v1/brands | POST | create → 201 | ✅ PASS |
| internal/v1/brands | POST | duplicate → 409 | ✅ PASS |
| internal/v1/brands/:id | PUT | update → 200 | ✅ PASS |
| internal/v1/brands/:id | DELETE | soft-delete → 204 | ✅ PASS |
| (no auth) | GET | → 401 | ✅ PASS |

### Self-Review Findings
| Severity | Finding | Resolution |
|----------|---------|------------|
| [HIGH] | Race condition on duplicate name | Added DB unique index |
| [MEDIUM] | Missing request_id in error logs | Added via NestJS context |

### Known Limitations
- AC-71000-023: needs E2E with product module
- AC-71000-026: [MISSING] in spec — PM decision pending

### Coverage Verification
- Command: `npm run test:cov`
- Result: ✅ PASS
- Overall: 91% lines, 84% branches, 100% functions
