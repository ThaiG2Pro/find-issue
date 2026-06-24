---
name: tasks-example
description: >
  Golden example of tasks.md — full S3 task breakdown with file paths, AC-ID references, checkpoints, and dependency order.
---

# Implementation Plan: CMS Brand Management

## Overview
CRUD API + CMS pages for brand management. Backend uses existing `brands` table with new unique index.

## Tasks

- [ ] 1. DB Migration — Add unique index
  - [ ] 1.1 Create migration for case-insensitive unique index
    - File: `apps/api/src/migrations/{timestamp}-AddBrandNameUniqueIndex.ts`
    - _Requirements: AC-71000-011, AC-71000-018, BR-71000-001, BR-71000-006_

- [ ] 2. Entity & DTOs
  - [ ] 2.1 Verify Brand entity has @DeleteDateColumn
    - File: `apps/api/src/modules/brand/entities/brand.entity.ts`
    - _Requirements: AC-71000-010, BR-71000-004, BR-71000-005_
  - [ ] 2.2 Create CreateBrandDto with validation
    - File: `apps/api/src/modules/brand/dto/create-brand.dto.ts`
    - _Requirements: AC-71000-008, AC-71000-012, AC-71000-013, AC-71000-014_
  - [ ] 2.3 Create UpdateBrandDto (PartialType)
    - File: `apps/api/src/modules/brand/dto/update-brand.dto.ts`
    - _Requirements: AC-71000-015, AC-71000-016, AC-71000-020_
  - [ ] 2.4 Create ListBrandsQueryDto
    - File: `apps/api/src/modules/brand/dto/list-brands-query.dto.ts`
    - _Requirements: AC-71000-002, AC-71000-003, AC-71000-007_
  - [ ] 2.5 Create BrandResponseDto
    - File: `apps/api/src/modules/brand/dto/brand-response.dto.ts`
    - _Requirements: AC-71000-001, AC-71000-009, AC-71000-016_

- [ ] 3. Service + Controller
  - [ ] 3.1 Implement BrandService (list, get, create, update, delete)
    - File: `apps/api/src/modules/brand/brand.service.ts`
    - _Requirements: AC-71000-001 through AC-71000-026_
  - [ ] 3.2 Create BrandController (5 endpoints)
    - File: `apps/api/src/modules/brand/brand.controller.ts`
    - _Requirements: AC-71000-001, AC-71000-008, AC-71000-015, AC-71000-021_
  - [ ] 3.3 Wire BrandModule
    - File: `apps/api/src/modules/brand/brand.module.ts`
    - _Requirements: All ACs_

- [ ] 4. Checkpoint — Backend API Review
  - 🔍 HUMAN REVIEW GATE — STOP and wait for user confirmation
  - Verify: tsc --noEmit passes, endpoints respond correctly, no secrets
  - _Requirements: All ACs_

- [ ] 5. Unit Tests
  - [ ] 5.1 Write BrandService unit tests
    - File: `apps/api/src/modules/brand/brand.service.spec.ts`
    - _Requirements: AC-71000-001 through AC-71000-026_

- [ ] 6. Integration Tests
  - [ ] 6.1 Write brand CRUD integration tests (real DB)
    - File: `apps/api/src/modules/brand/brand.controller.spec.ts`
    - _Requirements: AC-71000-001 through AC-71000-026_

- [ ] 7. CMS Frontend
  - [ ] 7.1 Types + API service
    - File: `apps/cms/src/types/brand.ts`
    - File: `apps/cms/src/services/api/brands.ts`
    - _Requirements: AC-71000-001, AC-71000-008_
  - [ ] 7.2 Brand list page
    - File: `apps/cms/src/views/brands/list/index.tsx`
    - _Requirements: AC-71000-001 through AC-71000-007, AC-71000-021, AC-71000-024_
  - [ ] 7.3 Brand form page (create/edit)
    - File: `apps/cms/src/views/brands/form/index.tsx`
    - _Requirements: AC-71000-008, AC-71000-009, AC-71000-011, AC-71000-015, AC-71000-016_
  - [ ] 7.4 Routing + navigation
    - File: `apps/cms/src/app/(dashboard)/brands/page.tsx`
    - _Requirements: AC-71000-001, AC-71000-008, AC-71000-015_

- [ ] 8. Checkpoint — Final Coverage & Security
  - 🔍 HUMAN REVIEW GATE — STOP and wait for user confirmation
  - Run `npm run test:cov` → verify ≥ 80%
  - Security scan on diff
  - Verify OpenAPI decorators complete
  - _Requirements: All ACs_
