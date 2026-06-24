---
name: commit-message-helper
description: >
  Format commit messages theo My Project conventional commits convention.
  Type, scope, subject, body, footer với ticket reference.
  Dùng khi cần gợi ý commit message từ mô tả changes.
---

# Commit Message Helper — My Project

Conventional commits aligned với `.kiro/context/conventions.md`.

## When to Activate

- Sau khi hoàn thành một task (S4/S6)
- Khi cần format commit message đúng chuẩn
- Review commit message trước khi push

## How to Use

```
Dùng skill commit-message-helper cho changes: thêm brand management API
Dùng skill commit-message-helper: vừa fix race condition ở inventory module
```

## Commit Format

```
<type>(<scope>): <subject>

[optional body — explain WHAT and WHY]

[optional footer: Refs: TICKET-ID]
```

## Types

| Type | Khi nào dùng |
|------|-------------|
| `feat` | Tính năng mới |
| `fix` | Bug fix |
| `docs` | Chỉ thay đổi documentation |
| `style` | Code style (formatting, semicolons) — không thay đổi logic |
| `refactor` | Refactor — không thay đổi behavior |
| `perf` | Cải thiện performance |
| `test` | Thêm hoặc cập nhật tests |
| `build` | Build system hoặc dependencies |
| `ci` | CI/CD configuration |
| `chore` | Các thay đổi khác (tooling...) |
| `revert` | Revert commit trước |

## Scopes

`voucher` · `eligibility` · `redemption` · `budget` · `auth` · `middleware` · `infra` · `config` · `deps` · `docs`

## Rules

- Subject: **lowercase**, **imperative mood** (`add` không phải `added`), **không có period** ở cuối
- Subject: max 100 characters
- Body: giải thích WHAT và WHY, không phải HOW
- Footer: `Refs: GIFT-123` nếu có ticket

## Examples

```bash
feat(product): add brand management API endpoints

Implement CRUD operations for brand management:
- Create brand with name uniqueness validation
- Update brand with conflict detection
- Soft delete with cascade to SKUs

Refs: GIFT-123
```

```bash
fix(order): resolve inventory deduction race condition

Use database transaction with row-level locking (SELECT FOR UPDATE)
to prevent concurrent requests causing negative stock.

Refs: GIFT-456
```

```bash
perf(inventory): replace N+1 query with single JOIN

Stock calculation previously made 1+N DB calls per order.
Single JOIN reduces from ~2s to ~200ms at 1k orders.

Refs: GIFT-789
```

```bash
test(product): add unit tests for ProductService.create

Cover happy path, duplicate name conflict (409), and
missing required fields (400). Bring coverage to 85%.
```

## Validation Checklist

- [ ] Type là một trong 11 types hợp lệ
- [ ] Scope là domain của My Project (hoặc bỏ scope nếu cross-cutting)
- [ ] Subject viết thường, imperative, không có dấu chấm cuối
- [ ] Subject ≤ 100 ký tự
- [ ] Có ticket reference nếu changes từ JIRA/task tracker
