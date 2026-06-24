---
name: api-design
description: >
  REST API design patterns cho NestJS + Fastify. Resource naming, status codes,
  error responses, OpenAPI documentation. Tuân thủ My Project conventions.
---

# API Design — My Project

Patterns cho NestJS REST API, align với `.kiro/context/conventions.md`.

## When to Activate

- Designing new API endpoints (S3 / S3-sketch)
- Reviewing API contracts (S5)
- Adding pagination, filtering, sorting
- Implementing error handling

## URL Structure

```
# Base: /api/v1/{resource} — plural, kebab-case
GET    /api/v1/products
GET    /api/v1/products/:id
POST   /api/v1/products
PUT    /api/v1/products/:id
PATCH  /api/v1/products/:id
DELETE /api/v1/products/:id

# Nested resources (max 2 levels)
GET    /api/v1/campaigns/:id/variants
POST   /api/v1/orders/:id/cancel    # Action verb (sparingly)
```

## Response Format (P1 Standard)

### Success
```json
{
  "data": { "id": "uuid", "name": "Product" },
  "meta": {
    "timestamp": "2026-03-30T10:30:00Z",
    "path": "/api/v1/products/uuid",
    "method": "GET"
  }
}
```

### Success with Pagination
```json
{
  "data": [...],
  "meta": {
    "timestamp": "2026-03-30T10:30:00Z",
    "path": "/api/v1/products",
    "method": "GET",
    "pagination": { "page": 1, "limit": 20, "total": 150, "totalPages": 8 }
  }
}
```

### Error
```json
{
  "errors": [
    { "code": "VALIDATION_ERROR", "message": "Invalid email format", "field": "email" }
  ],
  "meta": {
    "timestamp": "2026-03-30T10:30:00Z",
    "path": "/api/v1/users",
    "method": "POST",
    "statusCode": 400
  }
}
```

## HTTP Status Codes

| Code | When | Method |
|------|------|--------|
| 200 | Success | GET, PUT, PATCH |
| 201 | Created | POST |
| 204 | No Content | DELETE |
| 400 | Bad Request / Validation | Any |
| 401 | Unauthorized | Any |
| 403 | Forbidden | Any |
| 404 | Not Found | Any |
| 409 | Conflict | POST, PUT |
| 422 | Unprocessable Entity | POST, PUT, PATCH |
| 429 | Rate Limited | Any |
| 500 | Server Error | Any |

❌ NEVER return 200 for errors
❌ NEVER return error messages in `data` field

## NestJS Controller Pattern

```typescript
@ApiTags('products')
@Controller('api/v1/products')
export class ProductController {
  @Get()
  @ApiOperation({ summary: 'List products' })
  @ApiResponse({ status: 200, type: [ProductDto] })
  @ApiQuery({ name: 'page', required: false, type: Number })
  @ApiQuery({ name: 'limit', required: false, type: Number })
  async findAll(@Query() query: PaginationDto) {
    return this.productService.findAll(query);
  }

  @Post()
  @ApiOperation({ summary: 'Create product' })
  @ApiResponse({ status: 201, type: ProductDto })
  @ApiBody({ type: CreateProductDto })
  async create(@Body() dto: CreateProductDto) {
    return this.productService.create(dto);
  }
}
```

## DTO Validation

```typescript
export class CreateProductDto {
  @ApiProperty({ description: 'Product name', example: 'iPhone 15 Pro' })
  @IsString()
  @IsNotEmpty()
  name: string;

  @ApiProperty({ description: 'Price in VND', example: 29990000 })
  @IsNumber()
  @Min(0)
  price: number;

  @ApiPropertyOptional({ description: 'Description' })
  @IsString()
  @IsOptional()
  description?: string;
}
```

## Pagination

### Offset-Based (default cho CMS/admin)
```
GET /api/v1/products?page=2&limit=20
```

### Cursor-Based (cho high-volume APIs)
```
GET /api/v1/orders?cursor=eyJpZCI6MTIzfQ&limit=20
```

## Filtering & Sorting

```
GET /api/v1/products?status=active&category=electronics
GET /api/v1/products?sort=-created_at,price
GET /api/v1/products?q=wireless+headphones
```

## Rate Limiting (Redis-backed)

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640000000
```

| Tier | Limit | Use Case |
|------|-------|----------|
| Public | 30/min | Unauthenticated |
| Authenticated | 100/min | Standard API |
| Internal | 10000/min | Service-to-service |

## Checklist (S3 Design / S5 QA)

- [ ] URL follows `/api/v1/{resource}` (plural, kebab-case)
- [ ] Correct HTTP method and status codes
- [ ] Input validated with class-validator DTOs
- [ ] Response follows `{ data, meta, errors }` format
- [ ] Pagination on list endpoints
- [ ] Auth guards on protected endpoints
- [ ] Rate limiting configured
- [ ] OpenAPI decorators complete
- [ ] No internal details leaked in errors
