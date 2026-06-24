---
name: design-example
description: >
  Golden example of design.md — full S3 output for CMS Brand Management. Contains: Sketch/Gap Analysis, ADRs, DB Schema, API Design, Sequence Flows, Error Mapping, Implementation Guide.
---

# S3 — Full Design: CMS Brand Management

## Sketch — Gap Analysis

### ACs Reviewed
- AC-71000-001 through AC-71000-026: All 26 ACs reviewed

### BRs Reviewed
- BR-71000-001 through BR-71000-006: All 6 business rules reviewed

### Gaps Found
- GAP-001: AC-71000-026 [MISSING] — delete with active products undefined. Non-critical: proceed with soft-delete that does NOT block.
- No other critical gaps. Proceeding to full design.

---

## Architecture Overview

### System Components
```
CMS Frontend (React+MUI) → CMS Internal API (NestJS) → PostgreSQL (brands table)
                                    ↑ CmsAuthGuard (X-CMS-Api-Key)
```

### Module Structure
```
apps/api/src/modules/brand/
├── brand.module.ts
├── brand.controller.ts
├── brand.service.ts
├── dto/ (create, update, list-query, response)
└── entities/brand.entity.ts
```

## ADR (Architecture Decision Records)

### ADR-001: Case-Insensitive Uniqueness via DB Index
#### Context
Brand names must be unique regardless of casing.
#### Decision
Use `CREATE UNIQUE INDEX idx_brands_name_lower_active ON brands(LOWER(name)) WHERE deleted_at IS NULL`
#### Consequences
- **Positive**: Enforced at DB level, prevents race conditions
- **Negative**: Slightly slower inserts
#### Alternatives Considered
- Application-level only: race condition risk
#### Status: Accepted

### ADR-002: Soft Delete with TypeORM @DeleteDateColumn
#### Context
Brands referenced by products — hard delete breaks integrity.
#### Decision
Use `@DeleteDateColumn()` + `.softDelete()`. All queries auto-filter `deleted_at IS NULL`.
#### Consequences
- **Positive**: Historical data preserved, simple implementation
- **Negative**: Table grows over time
#### Status: Accepted

## API Design

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `internal/v1/brands` | List + search + pagination | X-CMS-Api-Key |
| GET | `internal/v1/brands/:id` | Get detail | X-CMS-Api-Key |
| POST | `internal/v1/brands` | Create | X-CMS-Api-Key |
| PUT | `internal/v1/brands/:id` | Update | X-CMS-Api-Key |
| DELETE | `internal/v1/brands/:id` | Soft delete | X-CMS-Api-Key |

## DB Schema

Existing table `brands` — add unique index:
```sql
CREATE UNIQUE INDEX idx_brands_name_lower_active ON brands(LOWER(name_vi)) WHERE deleted_at IS NULL;
CREATE INDEX idx_brands_name_search ON brands(name_vi varchar_pattern_ops) WHERE deleted_at IS NULL;
```

## Error Message Mapping

| Error Code | HTTP | Message | AC Reference |
|------------|------|---------|-------------|
| VALIDATION_ERROR | 400 | "Thông tin {field} là bắt buộc." | AC-71000-012,013,014 |
| DUPLICATE_BRAND_NAME | 409 | "Tên thương hiệu đã tồn tại." | AC-71000-011,018 |
| BRAND_NOT_FOUND | 404 | "Không tìm thấy thương hiệu." | AC-71000-019,025 |

## Sequence Flows

### Happy: Create Brand
```
CMS → Controller: POST internal/v1/brands {name}
→ Service: checkDuplicate(LOWER(name)) → save → 201 {data, meta}
```

### Error: Duplicate Name
```
CMS → Controller → Service: checkDuplicate → found → 409 {errors, meta}
```

## Implementation Guide

### Recommended Order
1. Migration: add index (ref: `1700000027000-AddCmsProductManagementIndexes.ts`)
2. Entity: verify brand.entity.ts
3. DTOs → Service → Controller → Module
4. Tests: unit → integration

### Patterns to Follow
- Pagination: existing controller patterns
- Error handling: `apps/api/src/core/filters/`
- Auth: `CmsAuthGuard` at controller level
- Soft delete: TypeORM `@DeleteDateColumn` + `.softDelete()`

### Gotchas
- Name uniqueness is case-insensitive — use LOWER() in queries
- `deleted_at IS NULL` auto-applied by TypeORM, but custom QueryBuilder needs explicit WHERE
- AC-71000-026 is [MISSING] — allow soft-delete regardless for now
