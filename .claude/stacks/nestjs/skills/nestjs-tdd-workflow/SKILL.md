---
name: nestjs-tdd-workflow
description: >
  TDD workflow cho NestJS + Jest. Unit tests (mock deps) + Integration tests (real test DB).
  Use when "TDD", "test driven", "write tests first", "red green refactor".
tags: [testing, nestjs]
---

# TDD Workflow — NestJS

Jest test patterns cho NestJS, align với company conventions.

## When to Activate

- Writing new features (S4 Build)
- Fixing bugs
- Refactoring code
- QA validation (S5)

## Coverage Requirements (P1)

- Minimum: **80%** for lines, branches, functions, statements
- Hard fail in CI if below threshold
- Exclude: DTOs, entities, config files, main.ts

## Test Types

| Type | Mock DB? | File Pattern | Focus |
|------|----------|-------------|-------|
| Unit | ✅ Yes | `{name}.spec.ts` | Business logic in isolation |
| Integration | ❌ No (real test DB) | `{name}.e2e-spec.ts` | API endpoints, DB operations |

## TDD Loop

1. **Write test** (from AC in requirements.md)
2. **Run test** → should FAIL: `npm test -- --testNamePattern="test name"`
3. **Write minimal code** to make test pass
4. **Run test** → should PASS
5. **Refactor** while keeping tests green
6. **Check coverage** → must be ≥80%

## Unit Test Template

```typescript
import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { OrderService } from './order.service';
import { OrderRepository } from './order.repository';

describe('OrderService', () => {
  let service: OrderService;
  let repo: jest.Mocked<OrderRepository>;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        OrderService,
        {
          provide: OrderRepository,
          useValue: {
            findOne: jest.fn(),
            find: jest.fn(),
            save: jest.fn(),
            softDelete: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get(OrderService);
    repo = module.get(OrderRepository);
  });

  afterEach(() => jest.clearAllMocks());

  it('should calculate total correctly', async () => {
    const items = [{ price: 100, quantity: 2 }, { price: 50, quantity: 1 }];
    expect(service.calculateTotal(items)).toBe(250);
  });

  it('should throw NotFoundException when order not found', async () => {
    repo.findOne.mockResolvedValue(null);
    await expect(service.findById('999')).rejects.toThrow(NotFoundException);
  });
});
```

## Integration Test Template

```typescript
import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../app.module';

describe('OrderController (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const module: TestingModule = await Test.createTestingModule({
      imports: [AppModule], // Real AppModule — real test DB
    }).compile();

    app = module.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
    await app.init();
  });

  afterAll(() => app.close());

  it('POST /api/v1/orders → 201 with data+meta', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/orders')
      .send({ pin: '1234', amount: 100 })
      .expect(201);

    expect(res.body.data).toHaveProperty('id');
    expect(res.body.meta).toHaveProperty('timestamp');
  });

  it('POST /api/v1/orders → 400 for invalid input', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/orders')
      .send({})
      .expect(400);

    expect(res.body.errors).toBeDefined();
  });
});
```

## Test Cases Checklist

- [ ] Happy path — valid input, expected output
- [ ] Error cases — invalid input, 400/404/409
- [ ] Edge cases — empty, null, boundary values
- [ ] Business rules — state transitions, calculations
- [ ] Auth — unauthorized (401), forbidden (403)
- [ ] Side effects — cache invalidation, queue messages

## Test Environment Setup

```bash
# 1. Copy test env
cp .env.example .env.test
# Set TEST_DB_* variables in .env.test

# 2. Run migrations on test DB
NODE_ENV=test npm run typeorm migration:run

# 3. Run tests
npm test                    # Unit tests only
npm run test:e2e            # Integration tests (real DB)
npm run test:cov            # With coverage report
```

### Environment Variables (.env.test)

```env
NODE_ENV=test
DB_HOST=localhost
DB_PORT=5432
DB_NAME={project}_test      # Separate test database — KHÔNG dùng production DB
DB_USERNAME=postgres
DB_PASSWORD=postgres
VALKEY_HOST=localhost
VALKEY_PORT=6379
```

### Jest Config Notes

- Unit tests: `src/**/*.spec.ts` — no DB required
- Integration tests: `src/**/*.e2e-spec.ts` — requires test DB running
- Coverage threshold: 80% enforced in `jest.config.ts`
- Exclude from coverage: `**/*.dto.ts`, `**/*.entity.ts`, `**/main.ts`, `**/config/**`

### CI/CD Test Flow

```bash
npm run lint               # 1. Lint
npm run build              # 2. Type check + compile
npm test -- --ci           # 3. Unit tests
npm run test:e2e -- --ci   # 4. Integration tests (với test DB service)
npm run test:cov           # 5. Coverage check
```

## Mock Patterns

```typescript
// Mock Repository
const mockRepo = {
  findOne: jest.fn(),
  find: jest.fn(),
  save: jest.fn(),
  softDelete: jest.fn(),
  createQueryBuilder: jest.fn(() => ({
    where: jest.fn().mockReturnThis(),
    andWhere: jest.fn().mockReturnThis(),
    leftJoinAndSelect: jest.fn().mockReturnThis(),
    getMany: jest.fn(),
    getOne: jest.fn(),
  })),
};

// Mock Cache (Valkey)
const mockCache = { get: jest.fn(), set: jest.fn(), invalidate: jest.fn() };

// Mock SQS Queue
const mockQueue = { enqueue: jest.fn() };
```

## Rules

- ✅ Unit tests: Mock repositories, external services, queues
- ❌ Integration tests: DO NOT mock database — dùng real test DB (`{project}_test`)
- ✅ Use separate test database — KHÔNG dùng production DB
- ✅ Clean up test data sau mỗi test (`afterEach` hoặc `afterAll`)
- ✅ Descriptive names: `should [expected] when [condition]`
- ✅ AAA pattern: Arrange → Act → Assert
- ✅ Each test independent — no shared state between tests
