---
name: nestjs-api-design
description: NestJS REST API design patterns — URL conventions, response format, DTOs, pagination, auth, rate limiting
tags: [api, nestjs]
---

# API Design — NestJS

## URL Structure

```
/api/v1/{resource}
```

- Plural, kebab-case: `/api/v1/order-items`
- Nested max 2 levels: `/api/v1/users/:userId/orders`

## Response Format (P1 Standard)

**Success:**
```json
{ "data": { ... }, "meta": { "timestamp": "...", "path": "...", "method": "..." } }
```

**List:**
```json
{ "data": [...], "meta": { "pagination": { "page": 1, "limit": 20, "total": 100, "totalPages": 5 } } }
```

**Error:**
```json
{ "errors": [{ "code": "VALIDATION_ERROR", "message": "...", "field": "email" }], "meta": { "statusCode": 422 } }
```

## HTTP Status Codes

| Code | Usage |
|------|-------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (delete) |
| 400 | Bad Request |
| 401 | Not Authenticated |
| 403 | Not Authorized |
| 404 | Not Found |
| 409 | Conflict |
| 422 | Validation Error |
| 429 | Rate Limited |
| 500 | Internal Server Error |

## NestJS Controller Pattern

```typescript
@ApiTags('orders')
@Controller('api/v1/orders')
export class OrdersController {
  @Get()
  @ApiOperation({ summary: 'List orders' })
  @ApiResponse({ status: 200, type: OrderListResponseDto })
  @ApiQuery({ name: 'page', required: false })
  @ApiQuery({ name: 'limit', required: false })
  async list(@Query() query: ListOrdersDto) { ... }

  @Post()
  @ApiOperation({ summary: 'Create order' })
  @ApiResponse({ status: 201, type: OrderResponseDto })
  @ApiBody({ type: CreateOrderDto })
  async create(@Body() dto: CreateOrderDto) { ... }
}
```

## DTO Validation

```typescript
export class CreateOrderDto {
  @ApiProperty({ description: 'Product ID' })
  @IsString()
  @IsNotEmpty()
  productId: string;

  @ApiProperty({ description: 'Quantity', minimum: 1 })
  @IsNumber()
  @Min(1)
  quantity: number;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  note?: string;
}
```

Use `class-validator` + `class-transformer`. Every request body/query must have a DTO.

## Pagination

**Offset-based** (CMS/admin):
```
GET /api/v1/orders?page=2&limit=20
```

**Cursor-based** (high-volume feeds):
```
GET /api/v1/notifications?cursor=eyJpZCI6MTIzfQ&limit=20
```

## Filtering & Sorting

```
GET /api/v1/products?status=active&category=electronics
GET /api/v1/products?sort=-created_at,price
GET /api/v1/products?q=keyword
```

- Filter by query params
- Sort with `-` prefix for descending
- `q` for full-text search

## Auth & Authorization

- **Bearer token** in `Authorization` header: `Authorization: Bearer <token>`
- Auth check **BEFORE** business logic — use NestJS guards
- Always check **ownership** to prevent IDOR: verify the requesting user owns/has access to the resource
- Distinguish **401** (not authenticated — missing/invalid token) vs **403** (not authorized — valid token but insufficient permissions)

```typescript
@UseGuards(JwtAuthGuard, OwnershipGuard)
@Get(':id')
async findOne(@Param('id') id: string, @CurrentUser() user: UserPayload) {
  // Guard already verified auth + ownership
}
```

## Rate Limiting

Valkey-backed, 3 tiers with `X-RateLimit-*` headers:

| Tier | Limit |
|------|-------|
| Public | 30/min |
| Authenticated | 100/min |
| Internal | 10,000/min |

## Checklist

- [ ] URL follows `/api/v1/{resource}` plural kebab-case
- [ ] Correct HTTP method (GET/POST/PUT/PATCH/DELETE)
- [ ] Request validated with class-validator DTOs
- [ ] Response uses `{ data, meta }` or `{ errors, meta }` format
- [ ] Pagination implemented (offset or cursor)
- [ ] Auth guards applied, ownership checked (no IDOR)
- [ ] 401 vs 403 correctly distinguished
- [ ] Rate limiting configured per tier
- [ ] OpenAPI decorators on every endpoint (@ApiTags, @ApiOperation, @ApiResponse)
- [ ] No internal details leaked in error responses

