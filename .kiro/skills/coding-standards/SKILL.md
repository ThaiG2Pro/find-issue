---
name: coding-standards
description: >
  Coding standards cho TypeScript/NestJS backend.
  Naming, typing, error handling, async patterns. Tuân thủ My Project conventions.
---

# Coding Standards — My Project

TypeScript standards, align với `.kiro/context/conventions.md`.

## When to Activate

- Writing or reviewing code (S4, S5)
- Refactoring existing code
- Onboarding new patterns

## Naming (P1 Standard)

| Element | Convention | Example |
|---------|-----------|---------|
| Files (backend) | kebab-case.ts | `user-profile.service.ts` |
| Files (frontend) | PascalCase.tsx | `UserProfile.tsx` |
| Classes | PascalCase | `UserService`, `OrderController` |
| Interfaces | PascalCase + I prefix | `IUserRepository` |
| Types | PascalCase | `UserRole`, `OrderStatus` |
| Functions/Methods | camelCase | `getUserById`, `calculateTotal` |
| Variables | camelCase | `userId`, `isActive` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_ATTEMPTS` |
| Enums | PascalCase name, UPPER_SNAKE values | `OrderStatus.PENDING` |
| DB tables | snake_case | `order_items` |
| DB columns | snake_case | `created_at` |

## TypeScript Patterns

### Type Safety
```typescript
// ✅ Explicit types
interface Market { id: string; name: string; status: 'active' | 'closed' }

// ❌ Never use any
function getMarket(id: any): Promise<any> { }
```

### Immutability
```typescript
// ✅ Spread operator
const updated = { ...user, name: 'New Name' };
const newList = [...items, newItem];

// ❌ Never mutate directly
user.name = 'New Name';
items.push(newItem);
```

### Guard Clauses
```typescript
// ✅ Early returns
async findById(id: string): Promise<User> {
  if (!id) throw new BadRequestException('ID required');
  const user = await this.repo.findOne({ where: { id } });
  if (!user) throw new NotFoundException(`User ${id} not found`);
  return user;
}

// ❌ Deep nesting
async findById(id: string) {
  if (id) {
    const user = await this.repo.findOne({ where: { id } });
    if (user) { return user; }
  }
}
```

### Async/Await
```typescript
// ✅ Parallel when independent
const [users, orders] = await Promise.all([
  this.userService.findAll(),
  this.orderService.findAll(),
]);

// ❌ Sequential when unnecessary
const users = await this.userService.findAll();
const orders = await this.orderService.findAll();
```

### Error Handling
```typescript
// ✅ Specific exceptions with context
try {
  const result = await this.externalApi.call(payload);
  return result;
} catch (error) {
  this.logger.error('External API failed', { error: error.message, payload_id: payload.id });
  throw new ServiceUnavailableException('External service unavailable');
}

// ❌ Generic catch, swallow errors
try { await doSomething(); } catch (e) { }
```

### Constants
```typescript
// ✅ Named constants
const MAX_RETRIES = 3;
const DEBOUNCE_DELAY_MS = 500;
const DEFAULT_PAGE_SIZE = 20;

// ❌ Magic numbers
if (retryCount > 3) { }
setTimeout(callback, 500);
```

## Code Smells to Avoid

- Functions > 20 lines → extract helpers
- Nesting > 4 levels → use guard clauses
- Parameters > 7 → use object parameter
- Cognitive complexity > 15 → simplify
- Duplicated logic → extract shared utility
- Unused imports/variables → remove

## Checklist

- [ ] Naming follows P1 conventions
- [ ] No `any` types
- [ ] Guard clauses over deep nesting
- [ ] Parallel async when possible
- [ ] Specific error handling with context
- [ ] Named constants, no magic numbers
- [ ] No unused code
- [ ] Self-documenting names (comments explain WHY, not WHAT)
