---
name: nestjs-api-documentation-checker
description: >
  Kiểm tra OpenAPI/Swagger decorator completeness trên NestJS controllers.
  @ApiTags, @ApiOperation, @ApiResponse, @ApiProperty trên DTOs.
  Dùng khi review controller file hoặc trước khi tạo PR (S4 gate).
tags: [api, nestjs]
---

# API Documentation Checker

OpenAPI compliance checker cho NestJS, align với company conventions.

## When to Activate

- Trước khi tạo PR từ S4 Build (triggered bởi hook `api-doc-reminder`)
- Khi review controller file
- S5 QA — verify API contract documentation đầy đủ

## How to Use

```
Dùng skill api-documentation-checker: apps/api/src/modules/products/product.controller.ts
Dùng skill api-documentation-checker để check toàn module: apps/api/src/modules/products/
```

## Checklist

### Controller Level
- [ ] `@ApiTags('resource-name')` present — kebab-case, plural
- [ ] Controller path: `/api/v1/{resource}` format

### Endpoint Level (mỗi handler)
- [ ] `@ApiOperation({ summary: '...' })` với summary có nghĩa
- [ ] `@ApiResponse()` cho success case (200, 201, hoặc 204)
- [ ] `@ApiResponse()` cho error cases (400, 401, 403, 404)
- [ ] `@ApiQuery()` cho mỗi query parameter
- [ ] `@ApiParam()` cho mỗi path parameter (`:id`, `:slug`...)
- [ ] `@ApiBody({ type: CreateXxxDto })` cho POST/PUT/PATCH

### HTTP Status Codes
| Method | Success | Common Errors |
|--------|---------|--------------|
| GET | 200 | 400, 401, 403, 404 |
| POST | 201 | 400, 401, 403, 409, 422 |
| PUT/PATCH | 200 | 400, 401, 403, 404, 409 |
| DELETE | 204 | 401, 403, 404 |

### DTO Documentation
- [ ] Mọi DTO property có `@ApiProperty()` hoặc `@ApiPropertyOptional()`
- [ ] Mỗi property có `description`
- [ ] Mỗi property có `example`
- [ ] Enums: `@ApiProperty({ enum: EnumType })`

### Response Format
- [ ] Success responses: `{ data, meta }` structure
- [ ] Error responses: `{ errors, meta }` structure
- [ ] List endpoints: `meta.pagination` included

## Reference Pattern

```typescript
@ApiTags('products')
@Controller('api/v1/products')
export class ProductController {

  @Get()
  @ApiOperation({ summary: 'List all products with pagination' })
  @ApiResponse({ status: 200, description: 'Success', type: [ProductResponseDto] })
  @ApiResponse({ status: 400, description: 'Bad Request' })
  @ApiResponse({ status: 401, description: 'Unauthorized' })
  @ApiQuery({ name: 'page', required: false, type: Number, example: 1 })
  @ApiQuery({ name: 'limit', required: false, type: Number, example: 20 })
  @ApiQuery({ name: 'status', required: false, enum: ProductStatus })
  async findAll(@Query() query: PaginationDto) { }

  @Post()
  @ApiOperation({ summary: 'Create a new product' })
  @ApiBody({ type: CreateProductDto })
  @ApiResponse({ status: 201, description: 'Created', type: ProductResponseDto })
  @ApiResponse({ status: 400, description: 'Validation Error' })
  @ApiResponse({ status: 409, description: 'Product name already exists' })
  async create(@Body() dto: CreateProductDto) { }
}
```

## Output Format

```markdown
## API Doc Check: ProductController

### ❌ Critical (Must Fix)
- `findAll`: Missing @ApiResponse for 401
- `ProductDto.price`: Missing @ApiProperty

### ⚠️ Warning (Should Fix)
- `create`: Missing @ApiResponse for 409 (conflict)
- `ProductDto.description`: Missing `example` in @ApiProperty

### ✅ Passed
- @ApiTags present
- All endpoints have @ApiOperation
- Response format correct (data/meta)

### Summary: 4 endpoints | Critical: 2 | Warning: 2 | Passed: 8 | Score: 67%
```
