---
name: nestjs-test-generator
description: >
  Generate unit và integration tests cho NestJS services/controllers.
  Use when "generate tests", "create test cases", "add tests for", "test coverage".
  Align với nestjs-tdd-workflow patterns.
tags: [testing, nestjs]
---

# Test Generator — NestJS

Test generation patterns cho NestJS, align với `nestjs-tdd-workflow` skill và company conventions.

## When to Activate

- Bắt đầu viết tests cho service/controller mới (S4)
- Generate test scenarios từ AC trong `requirements.md` (S5)
- Khi cần tăng coverage lên ≥80%

## How to Use

```
Dùng skill nestjs-test-generator cho: src/modules/users/user.service.ts
Dùng skill nestjs-test-generator để generate integration tests cho: product.controller.ts
```

## Coverage Requirements (P1)

- **Minimum**: 80% lines, branches, functions, statements
- **Hard fail** in CI if below threshold
- **Exclude**: DTOs, entities, config files, `main.ts`

## Unit Test Template

```typescript
import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { ProductService } from './product.service';
import { ProductRepository } from './product.repository';

describe('ProductService', () => {
  let service: ProductService;
  let repo: jest.Mocked<ProductRepository>;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ProductService,
        {
          provide: ProductRepository,
          useValue: {
            findOne: jest.fn(),
            find: jest.fn(),
            save: jest.fn(),
            softDelete: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get(ProductService);
    repo = module.get(ProductRepository);
  });

  afterEach(() => jest.clearAllMocks());

  describe('findById', () => {
    it('should return product when found', async () => {
      const product = { id: 'uuid-1', name: 'iPhone 15', status: 'active' };
      repo.findOne.mockResolvedValue(product as any);

      const result = await service.findById('uuid-1');

      expect(result).toEqual(product);
      expect(repo.findOne).toHaveBeenCalledWith({ where: { id: 'uuid-1', deletedAt: null } });
    });

    it('should throw NotFoundException when product not found', async () => {
      repo.findOne.mockResolvedValue(null);

      await expect(service.findById('not-exist')).rejects.toThrow(NotFoundException);
    });
  });

  describe('create', () => {
    it('should create product successfully', async () => {
      const dto = { name: 'New Product', price: 100000 };
      const saved = { id: 'uuid-2', ...dto };
      repo.save.mockResolvedValue(saved as any);

      const result = await service.create(dto as any);

      expect(result).toEqual(saved);
      expect(repo.save).toHaveBeenCalledWith(expect.objectContaining(dto));
    });

    it('should throw ConflictException when name already exists', async () => {
      repo.save.mockRejectedValue({ code: '23505' }); // PG unique violation

      await expect(service.create({ name: 'Duplicate' } as any)).rejects.toThrow();
    });
  });
});
```

## Integration Test Template

```typescript
import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../app.module';

describe('ProductController (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const module: TestingModule = await Test.createTestingModule({
      imports: [AppModule], // Real AppModule — no DB mock
    }).compile();

    app = module.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }));
    await app.init();
  });

  afterAll(() => app.close());

  it('POST /api/v1/products → 201 with data+meta', () => {
    return request(app.getHttpServer())
      .post('/api/v1/products')
      .send({ name: 'Test Product', price: 50000 })
      .expect(201)
      .expect((res) => {
        expect(res.body.data).toHaveProperty('id');
        expect(res.body.meta).toHaveProperty('timestamp');
      });
  });

  it('POST /api/v1/products → 400 for missing required fields', () => {
    return request(app.getHttpServer())
      .post('/api/v1/products')
      .send({})
      .expect(400)
      .expect((res) => {
        expect(res.body.errors).toBeDefined();
      });
  });

  it('GET /api/v1/products/:id → 404 for non-existent id', () => {
    return request(app.getHttpServer())
      .get('/api/v1/products/00000000-0000-0000-0000-000000000000')
      .expect(404);
  });
});
```

## Test Cases Checklist

### From AC (requirements.md)
- [ ] Mỗi AC có ít nhất 1 test case tương ứng
- [ ] Happy path — valid input, expected output, đúng status code
- [ ] Error path — invalid input, missing data, expected error response
- [ ] Edge cases — empty, null, boundary values, concurrent requests

### Business Logic
- [ ] State transitions tested (PENDING → ACTIVE → INACTIVE)
- [ ] Side effects: cache invalidation, queue enqueue, event emit
- [ ] Idempotency (gọi lại không gây duplicate)

### Auth
- [ ] Unauthorized (401) khi thiếu token
- [ ] Forbidden (403) khi sai role

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

// Mock Cache Service (Valkey)
const mockCache = { get: jest.fn(), set: jest.fn(), invalidate: jest.fn() };

// Mock SQS Queue
const mockQueue = { enqueue: jest.fn() };
```
