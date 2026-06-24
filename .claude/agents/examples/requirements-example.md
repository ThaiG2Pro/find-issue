---
name: requirements-example
description: >
  Golden example of requirements.md — full S1+S2 output for CMS Brand Management.
  Use as pattern reference when writing requirements.md for any feature.
  Contains: Problem Statement, User Stories, ACs with tags, BRs, Edge Cases, Structured Extract.
---

# CMS Brand Management — Requirements & Functional Specification

## S1 — Requirement Pack

### Problem Statement
CMS Giftport hiện chưa có giao diện quản lý thương hiệu (Brand). Operator phải thao tác trực tiếp qua database. Cần xây dựng trang CMS cho phép operator CRUD brands với phân trang, tìm kiếm, tạo mới, chỉnh sửa và soft-delete.

### KPIs
- **Task completion time**: Operator tạo brand mới < 30 giây
- **API response time**: GET list < 500ms, POST/PUT < 1s (95th percentile)
- **Error rate**: < 1% cho valid requests

### Scope
#### In Scope
- CRUD API endpoints (internal CMS API)
- CMS pages: list, create/edit form
- Input validation, error handling, OpenAPI docs

#### Out Scope
- Brand logo upload, import/export CSV, brand hierarchy

### Stakeholders
- **Primary**: CMS Operators
- **Technical**: Backend team, Frontend team, QC team

### Constraints
#### Technical Constraints
- Existing `brands` table, NestJS + Fastify, CMS React + MUI + Vuexy
- Response format: `{ data, meta, errors }`, CMS API prefix: `internal/v1/`

#### Business Constraints
- Brand referenced by products — no hard delete
- Brand name unique (case-insensitive), max 255 chars

### Open Questions
- OQ-001: Brand có cần trường `code` tự generate không? — PM confirm

### Risk Assessment
- **HIGH**: Duplicate name race condition — DB unique index mitigates
- **MEDIUM**: Soft-delete cascade to product display

### Edge Cases
1. Create brand with existing name (case-insensitive)
2. Create brand with whitespace-only name
3. Create brand with special characters (emoji, HTML)
4. Update brand name to existing name of another brand
5. Delete brand referenced by 50+ products
6. Double-delete already soft-deleted brand
7. Get brand with invalid UUID format
8. Get brand with valid UUID but non-existent
9. List brands with 10,000+ records
10. Search with query > 255 chars
11. Concurrent create 2 brands same name
12. Update with empty payload
13. Description exceeding 1000 chars
14. Network loss during form submit

---

## S2 — Functional Specification

### User Stories

#### US-1: List Brands
**As a** CMS Operator **I want** to view a paginated list of brands **So that** I can find and manage brands

#### US-2: Create Brand
**As a** CMS Operator **I want** to create a new brand **So that** new brands are available for products

#### US-3: Edit Brand
**As a** CMS Operator **I want** to update a brand **So that** brand data stays accurate

#### US-4: Delete Brand
**As a** CMS Operator **I want** to soft-delete a brand **So that** it's hidden but historical data preserved

### Acceptance Criteria

#### US-1: List Brands
##### Happy Path
- AC-71000-001: [CONFIRMED] **Given** brands exist **When** Operator navigates to Brands page **Then** table displays name, description, created_at, actions
- AC-71000-002: [CONFIRMED] **Given** list loaded **When** rendered **Then** pagination shows with default page=1, limit=20
- AC-71000-003: [CONFIRMED] **Given** Operator types "apple" **When** presses Enter **Then** resets to page 1, shows matching brands (case-insensitive)

##### Error Path
- AC-71000-005: [CONFIRMED] **Given** API returns 500 **When** loading list **Then** error alert with retry button
- AC-71000-006: [CONFIRMED] **Given** no brands match **When** search empty **Then** "Không tìm thấy thương hiệu nào"
- AC-71000-007: [ASSUMED] **Given** page=0 or limit=1001 **When** API receives **Then** returns 400 VALIDATION_ERROR

#### US-2: Create Brand
##### Happy Path
- AC-71000-008: [CONFIRMED] **Given** on Brands page **When** clicks "Thêm mới" **Then** navigates to create form
- AC-71000-009: [CONFIRMED] **Given** valid data **When** clicks "Lưu" **Then** 201, redirect to list, success toast
- AC-71000-010: [CONFIRMED] **Given** created **When** saved **Then** auto UUID, created_at, updated_at, deleted_at=null

##### Error Path
- AC-71000-011: [CONFIRMED] **Given** name "Apple" exists **When** submit "apple" **Then** 409 DUPLICATE_BRAND_NAME
- AC-71000-012: [CONFIRMED] **Given** empty name **When** submit **Then** inline error, no API call
- AC-71000-013: [ASSUMED] **Given** name > 255 chars **When** API validates **Then** 400 VALIDATION_ERROR
- AC-71000-014: [ASSUMED] **Given** description > 1000 chars **When** API validates **Then** 400 VALIDATION_ERROR

#### US-3: Edit Brand
##### Happy Path
- AC-71000-015: [CONFIRMED] **Given** clicks edit **When** loads **Then** form pre-filled
- AC-71000-016: [CONFIRMED] **Given** valid unique name **When** saves **Then** 200, redirect, toast
- AC-71000-017: [CONFIRMED] **Given** updated **When** saved **Then** only updated_at changes

##### Error Path
- AC-71000-018: [CONFIRMED] **Given** changes to existing name **When** submit **Then** 409
- AC-71000-019: [ASSUMED] **Given** non-existent ID **When** loads **Then** 404 BRAND_NOT_FOUND
- AC-71000-020: [ASSUMED] **Given** no changes **When** submit **Then** 200 (idempotent)

#### US-4: Delete Brand
##### Happy Path
- AC-71000-021: [CONFIRMED] **Given** clicks delete + confirms **When** processed **Then** 204, removed from list, toast
- AC-71000-022: [CONFIRMED] **Given** soft-deleted **When** list queried **Then** not in results
- AC-71000-023: [ASSUMED] **Given** soft-deleted **When** product detail **Then** brand name still shows

##### Error Path
- AC-71000-024: [CONFIRMED] **Given** clicks delete **When** cancels **Then** no action
- AC-71000-025: [ASSUMED] **Given** already deleted **When** delete again **Then** 404
- AC-71000-026: [MISSING] **Given** brand has active products **When** delete **Then** {undefined — PM decision needed}

### Business Rules
- BR-71000-001: Brand name unique (case-insensitive) among active brands
- BR-71000-002: Soft-delete only, never hard delete
- BR-71000-003: Deleted brands excluded from list/search by default
- BR-71000-004: Name 1–255 chars, trimmed
- BR-71000-005: Description optional, max 1000 chars
- BR-71000-006: Uniqueness check excludes soft-deleted brands

### Error States
| HTTP Status | Error Code | Description |
|-------------|-----------|-------------|
| 400 | VALIDATION_ERROR | Missing/invalid input |
| 401 | UNAUTHORIZED | Missing X-CMS-Api-Key |
| 404 | BRAND_NOT_FOUND | Not found or deleted |
| 409 | DUPLICATE_BRAND_NAME | Name exists |
| 500 | INTERNAL_ERROR | Server error |

### Integration Points
- INT-71000-001: CMS Frontend → CMS API (brandService)
- INT-71000-002: CMS API → brands table (TypeORM)
- INT-71000-003: CMS API → products table (reference check)

### Non-functional Requirements
- **Performance**: GET < 500ms, POST/PUT < 1s, DELETE < 500ms
- **Security**: X-CMS-Api-Key auth, input validation, parameterized queries

### Figma Design
Figma: N/A

---
## _Structured Extract

### AC List
- AC-71000-001: [CONFIRMED] Brand list table with columns
- AC-71000-002: [CONFIRMED] Pagination default page=1, limit=20
- AC-71000-003: [CONFIRMED] Search case-insensitive
- AC-71000-005: [CONFIRMED] Error alert on API 500
- AC-71000-006: [CONFIRMED] Empty state message
- AC-71000-007: [ASSUMED] 400 on invalid pagination
- AC-71000-008: [CONFIRMED] Navigate to create form
- AC-71000-009: [CONFIRMED] Create → 201, redirect, toast
- AC-71000-010: [CONFIRMED] Auto UUID + timestamps
- AC-71000-011: [CONFIRMED] 409 duplicate name
- AC-71000-012: [CONFIRMED] Client-side empty name validation
- AC-71000-013: [ASSUMED] 400 name > 255
- AC-71000-014: [ASSUMED] 400 description > 1000
- AC-71000-015: [CONFIRMED] Edit form pre-filled
- AC-71000-016: [CONFIRMED] Update → 200, redirect, toast
- AC-71000-017: [CONFIRMED] Only updated_at changes
- AC-71000-018: [CONFIRMED] 409 duplicate on edit
- AC-71000-019: [ASSUMED] 404 non-existent brand
- AC-71000-020: [ASSUMED] Idempotent update
- AC-71000-021: [CONFIRMED] Soft-delete → 204
- AC-71000-022: [CONFIRMED] Deleted excluded from list
- AC-71000-023: [ASSUMED] Deleted brand on product detail
- AC-71000-024: [CONFIRMED] Cancel delete → no action
- AC-71000-025: [ASSUMED] 404 double-delete
- AC-71000-026: [MISSING] Delete with active products

### Business Rules
- BR-71000-001: Name unique case-insensitive among active
- BR-71000-002: Soft-delete only
- BR-71000-003: Deleted excluded from queries
- BR-71000-004: Name 1-255, trimmed
- BR-71000-005: Description optional, max 1000
- BR-71000-006: Uniqueness excludes deleted

### Integration Points
- INT-71000-001: CMS Frontend → CMS API
- INT-71000-002: CMS API → brands table
- INT-71000-003: CMS API → products table

### Risk Flags
- RISK-001: Duplicate name race condition — HIGH
- RISK-002: Soft-delete cascade — MEDIUM

### Metadata
ticket_id: 71000
domain: product
has_figma: false
has_cms_ui: true
actors: [operator]
ac_count: 26
ac_confirmed: 16
ac_assumed: 8
ac_missing: 1
ac_unclear: 0
