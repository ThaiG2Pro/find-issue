---
name: test-generator
description: >
  Generate unit tests và integration tests cho NestJS services/controllers.
  Coverage ≥80%, happy path + error path + edge cases. Vitest + Supertest.
  Align với DDD Clean Architecture + docs/30-architecture/09-implementation-constraints.md.
---

# Test Generator — My Project

Test generation patterns cho NestJS + Vitest, align với `.kiro/context/conventions.md`.

## When to Activate

- Viết tests cho domain service / use case / controller
- Generate test scenarios từ docs/knowledge/SPEC-XX.md
- Khi cần tăng coverage lên ≥80%

## Coverage Requirements (P1)

- **Minimum**: 80% lines, branches, functions, statements
- **Framework**: Vitest 4 + Supertest
- **Exclude**: DTOs, config files, `main.ts`, Prisma generated

## Unit Test Template — Domain Service

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { VoucherAggregate } from './voucher.aggregate';
import { VoucherNotActiveError, VoucherAlreadyReservedError } from '../errors';

describe('VoucherAggregate', () => {
  let aggregate: VoucherAggregate;

  beforeEach(() => {
    aggregate = VoucherAggregate.create({
      voucherId: 1,
      code: '7132616187',
      state: 3, // RECEIVED = active
      value: 100000,
      productId: 456,
      reservations: [],
      usage: null,
    });
  });

  describe('reserve()', () => {
    it('should reserve active voucher (INV-1 + INV-2)', () => {
      aggregate.reserve('BILL-001', 123, { transactionId: 'tx_1' });

      expect(aggregate.state).toBe(0); // CREATED = reserved
      expect(aggregate.reservations).toHaveLength(1);
      expect(aggregate.reservations[0].billNumber).toBe('BILL-001');
      expect(aggregate.reservations[0].oldStage).toBe(3);
    });

    it('should throw VoucherNotActiveError for used voucher (INV-1)', () => {
      aggregate = VoucherAggregate.create({ ...aggregate.snapshot(), state: 4 }); // USED

      expect(() => aggregate.reserve('BILL-001', 123, {}))
        .toThrow(VoucherNotActiveError);
    });

    it('should throw VoucherAlreadyReservedError (INV-2)', () => {
      aggregate.reserve('BILL-001', 123, {});

      expect(() => aggregate.reserve('BILL-002', 456, {}))
        .toThrow(VoucherAlreadyReservedError);
    });
  });
});
```

## Unit Test Template — Use Case (Command)

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ReserveVoucherCommand } from './reserve-voucher.command';

describe('ReserveVoucherCommand', () => {
  let command: ReserveVoucherCommand;
  let voucherRepo: any;
  let eligibilityChecker: any;
  let budgetService: any;
  let transactionManager: any;
  let distributedLock: any;

  beforeEach(() => {
    voucherRepo = {
      loadByCodeForUpdate: vi.fn(),
      save: vi.fn(),
    };
    eligibilityChecker = { evaluate: vi.fn() };
    budgetService = { reserve: vi.fn() };
    transactionManager = { execute: vi.fn((fn) => fn()) };
    distributedLock = {
      acquireProductLocks: vi.fn().mockResolvedValue([]),
      releaseLocks: vi.fn(),
    };

    command = new ReserveVoucherCommand(
      voucherRepo, eligibilityChecker, budgetService,
      transactionManager, distributedLock,
    );
  });

  it('should reserve voucher successfully', async () => {
    const voucher = createMockVoucher({ state: 3 }); // active
    voucherRepo.loadByCodeForUpdate.mockResolvedValue(voucher);
    eligibilityChecker.evaluate.mockResolvedValue({ eligible: true });

    const result = await command.execute({
      codes: ['7132616187'],
      billNumber: 'BILL-001',
      merchantContext: { storeId: 123, brandId: 456 },
    });

    expect(result.success).toBe(true);
    expect(voucherRepo.save).toHaveBeenCalled();
  });

  it('should rollback on eligibility fail', async () => {
    const voucher = createMockVoucher({ state: 3 });
    voucherRepo.loadByCodeForUpdate.mockResolvedValue(voucher);
    eligibilityChecker.evaluate.mockRejectedValue(
      new VoucherNotEligibleError('GI_VOUCHER_UNUSABLE_IN_STORE')
    );

    const result = await command.execute({ ... });

    expect(result.success).toBe(false);
    expect(result.returnCode).toBe('206');
    expect(distributedLock.releaseLocks).toHaveBeenCalled();
  });
});
```

## Integration Test Template — API Endpoint

```typescript
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { Test } from '@nestjs/testing';
import { FastifyAdapter, NestFastifyApplication } from '@nestjs/platform-fastify';
import { AppModule } from '../app.module';
import * as request from 'supertest';

describe('POST /v6.0/checkmultiple', () => {
  let app: NestFastifyApplication;

  beforeAll(async () => {
    const module = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = module.createNestApplication(new FastifyAdapter());
    await app.init();
    await app.getHttpAdapter().getInstance().ready();
  });

  afterAll(() => app.close());

  it('should return valid voucher info', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v6.0/checkmultiple')
      .send({ pin: '1234', codes: ['7132616187'] })
      .expect(200);

    expect(res.body.success).toBe(true);
    expect(res.body.data[0]).toHaveProperty('code');
    expect(res.body.data[0]).toHaveProperty('voucher_type');
  });

  it('should return error for invalid PIN', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v6.0/checkmultiple')
      .send({ pin: 'wrong', codes: ['7132616187'] })
      .expect(200); // PHP returns 200 for business errors

    expect(res.body.success).toBe(false);
    expect(res.body.return_code).toBe('200'); // GI_PIN_INVALID
  });
});
```

## Test Cases Checklist

### Per Spec (from docs/knowledge/SPEC-XX.md)
- [ ] Happy path — valid input, expected output
- [ ] Error mapping — each error code from knowledge file has a test
- [ ] Edge cases — boundary values, concurrent requests

### Domain (Aggregate + Services)
- [ ] Each invariant (INV-1 through INV-8) has a test
- [ ] State transitions: active→reserved, reserved→used, reserved→active
- [ ] Domain errors thrown correctly

### Use Cases
- [ ] Transaction rollback on failure
- [ ] Lock acquire + release (including on error)
- [ ] Query: errors as data, not exceptions
- [ ] Events dispatch after commit (UseVoucher only)

## Mock Patterns (Vitest)

```typescript
// Mock Port — IVoucherRepository
const mockRepo = {
  loadByCode: vi.fn(),
  loadByCodeForUpdate: vi.fn(),
  save: vi.fn(),
};

// Mock Port — IEligibilityChecker
const mockEligibility = {
  evaluate: vi.fn().mockResolvedValue({ eligible: true, ruleResults: [] }),
};

// Mock Port — IBudgetService
const mockBudget = {
  checkAvailability: vi.fn().mockResolvedValue(true),
  reserve: vi.fn(),
  commit: vi.fn(),
  release: vi.fn(),
};

// Mock Port — ITransactionManager
const mockTx = {
  execute: vi.fn((fn) => fn()), // execute callback immediately
};

// Mock Port — IDistributedLock
const mockLock = {
  acquireProductLocks: vi.fn().mockResolvedValue([]),
  releaseLocks: vi.fn(),
};

// Mock Port — IEventPublisher
const mockEvents = {
  publishVoucherUsed: vi.fn(),
};
```
