---
name: nestjs-backend-patterns
description: >
  Backend patterns cho NestJS + Fastify + TypeORM + Aurora PostgreSQL.
  Service/repository layers, error handling, caching (Valkey), async jobs (SQS).
tags: [backend, nestjs]
---

# Backend Patterns

NestJS architecture patterns, align với project structure conventions và tech stack conventions.

## When to Activate

- Implementing service/repository layers (S4)
- Designing module structure (S3)
- Adding caching, queues, error handling
- Optimizing database queries

## Module Structure

```
modules/<domain>/
├── <domain>.module.ts
├── <domain>.controller.ts    # Thin: validate → service → response
├── <domain>.service.ts       # Business logic + orchestration
├── <domain>.repository.ts    # DB access encapsulation
├── dto/
│   ├── create-<domain>.dto.ts
│   ├── update-<domain>.dto.ts
│   └── <domain>-response.dto.ts
└── entities/
    └── <domain>.entity.ts
```

## Layer Responsibilities

### Controller — Thin, no business logic
```typescript
@Controller('api/v1/products')
export class ProductController {
  constructor(private readonly productService: ProductService) {}

  @Post()
  async create(@Body() dto: CreateProductDto) {
    return this.productService.create(dto);
  }
}
```

### Service — Business logic + orchestration
```typescript
@Injectable()
export class ProductService {
  constructor(
    private readonly productRepo: ProductRepository,
    private readonly cacheService: CacheService,
  ) {}

  async create(dto: CreateProductDto): Promise<Product> {
    const product = await this.productRepo.save(dto);
    await this.cacheService.invalidate(`products:list`);
    return product;
  }
}
```

### Repository — Encapsulate DB access
```typescript
@Injectable()
export class ProductRepository {
  constructor(
    @InjectRepository(ProductEntity)
    private readonly repo: Repository<ProductEntity>,
  ) {}

  async findByStatus(status: string): Promise<ProductEntity[]> {
    return this.repo
      .createQueryBuilder('p')
      .where('p.status = :status', { status })
      .andWhere('p.deletedAt IS NULL')
      .getMany();
  }
}
```

## Base Entity (P1 Standard)

```typescript
@Entity()
export abstract class BaseEntity {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @CreateDateColumn({ name: 'created_at' })
  createdAt: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updatedAt: Date;

  @DeleteDateColumn({ name: 'deleted_at', nullable: true })
  deletedAt?: Date;
}
```

## Query Patterns

### Prevent N+1
```typescript
// ❌ Bad: N+1
const orders = await this.orderRepo.find();
for (const order of orders) {
  order.items = await this.itemRepo.findByOrderId(order.id);
}

// ✅ Good: JOIN
const orders = await this.orderRepo
  .createQueryBuilder('o')
  .leftJoinAndSelect('o.items', 'i')
  .getMany();
```

### Batch Operations
```typescript
// ❌ Bad: Loop insert
for (const item of items) {
  await this.repo.save(item);
}

// ✅ Good: Bulk insert
await this.repo.save(items);
```

### Transaction
```typescript
async createOrderWithItems(dto: CreateOrderDto): Promise<Order> {
  return this.dataSource.transaction(async (manager) => {
    const order = await manager.save(Order, dto.order);
    const items = dto.items.map(i => ({ ...i, orderId: order.id }));
    await manager.save(OrderItem, items);
    return order;
  });
}
```

## Caching (Valkey)

```typescript
@Injectable()
export class CacheService {
  constructor(@Inject('VALKEY') private readonly client: Redis) {}

  async getOrSet<T>(key: string, ttl: number, fetcher: () => Promise<T>): Promise<T> {
    const cached = await this.client.get(key);
    if (cached) return JSON.parse(cached);

    const data = await fetcher();
    await this.client.setex(key, ttl, JSON.stringify(data));
    return data;
  }

  async invalidate(pattern: string): Promise<void> {
    const keys = await this.client.keys(pattern);
    if (keys.length) await this.client.del(...keys);
  }
}
```

Rules:
- Cache is NOT source of truth
- Define TTL intentionally
- Invalidate after data changes
- Use stable, descriptive key naming: `{domain}:{id}:{field}`

## Async Jobs (SQS)

```typescript
@Injectable()
export class OrderQueueService {
  constructor(@Inject('SQS') private readonly sqs: SQSClient) {}

  async enqueue(orderId: string, action: string): Promise<void> {
    await this.sqs.send(new SendMessageCommand({
      QueueUrl: process.env.ORDER_QUEUE_URL,
      MessageBody: JSON.stringify({ orderId, action }),
      MessageGroupId: orderId, // FIFO dedup
    }));
  }
}
```

Rules:
- Every job MUST be idempotent
- Retries MUST be safe
- Include correlation/request IDs
- Heavy processing → always async

## Error Handling

```typescript
// Domain-specific exceptions
export class ProductNotFoundException extends NotFoundException {
  constructor(id: string) {
    super({ code: 'PRODUCT_NOT_FOUND', message: `Product ${id} not found` });
  }
}

// Global exception filter
@Catch()
export class GlobalExceptionFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse();
    const request = ctx.getRequest();

    const status = exception instanceof HttpException
      ? exception.getStatus()
      : HttpStatus.INTERNAL_SERVER_ERROR;

    response.status(status).send({
      errors: [{ code: 'INTERNAL_ERROR', message: 'Something went wrong' }],
      meta: { timestamp: new Date().toISOString(), path: request.url, statusCode: status },
    });
  }
}
```

## Logging (P1 Standard)

```typescript
// ✅ Good
this.logger.log({
  message: 'Order created',
  context: 'OrderService',
  request_id: requestId,
  user_id: userId,
  action: 'create_order',
  duration_ms: Date.now() - start,
  metadata: { order_id: order.id, total: order.total },
});

// ❌ Never log: passwords, tokens, PII, credit cards, secret keys
```

## Checklist

- [ ] Module follows `modules/<domain>/` structure
- [ ] Controller is thin — no business logic
- [ ] Service owns business logic
- [ ] Repository encapsulates DB access
- [ ] Base entity fields: id, created_at, updated_at, deleted_at
- [ ] No N+1 queries
- [ ] Transactions for multi-table writes
- [ ] Cache with TTL, invalidation on write
- [ ] Heavy processing via SQS
- [ ] Structured JSON logging, no PII
- [ ] Domain-specific exceptions
