---
name: laravel-api-design
description: >
  Laravel REST API design patterns. Covers URL structure, status codes,
  response format, pagination, filtering, auth, JsonResource, FormRequest,
  Scribe documentation, rate limiting.
tags: [api, laravel]
---

# API Design — Laravel

Merged patterns from ai-sdlc (universal) and the Laravel stack pack.

## When to Activate

- Designing new API endpoints (S3 / S3-sketch)
- Reviewing API contracts (S5)
- Adding pagination, filtering, sorting

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

## HTTP Methods & Status Codes

| Code | When | Method |
|------|------|--------|
| 200 | Success | GET, PUT, PATCH |
| 201 | Created | POST |
| 204 | No Content | DELETE |
| 400 | Bad Request / Validation | Any |
| 401 | Unauthenticated | Any |
| 403 | Forbidden (has identity, lacks permission) | Any |
| 404 | Not Found | Any |
| 409 | Conflict | POST, PUT |
| 422 | Unprocessable Entity | POST, PUT, PATCH |
| 429 | Rate Limited | Any |
| 500 | Server Error | Any |

❌ NEVER return 200 for errors
❌ NEVER return error messages in `data` field

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
    "statusCode": 422
  }
}
```

### Laravel Helpers

```php
// Success
return apiSuccess($data, 200);

// Error
return apiError('VALIDATION_ERROR', 'Invalid email format', 422);

// Paginated (see Pagination section)
return apiPaginated($query, $limit);
```

## Pagination

### Offset-Based (default)
```
GET /api/v1/products?page=2&limit=20
```

### limit/skip/get Pattern (avoids COUNT(*))

Key insight: avoid `COUNT(*)` on large tables. Use `limit + 1` trick to detect `has_more`.

```php
// In Service/Repository
public function list(int $limit = 20, int $skip = 0): array
{
    $items = Product::query()
        ->orderByDesc('created_at')
        ->skip($skip)
        ->limit($limit + 1)
        ->get();

    $hasMore = $items->count() > $limit;

    return [
        'data' => $items->take($limit),
        'meta' => [
            'page' => (int) floor($skip / $limit) + 1,
            'per_page' => $limit,
            'has_more' => $hasMore,
        ],
    ];
}

// apiPaginated() helper — use when available
return apiPaginated($query, $limit, $skip);
// Optional $total param only when COUNT is acceptable (small tables)
return apiPaginated($query, $limit, $skip, $total);
```

## Filtering & Sorting

```
GET /api/v1/products?status=active&category=electronics
GET /api/v1/products?sort=-created_at,price
GET /api/v1/products?q=wireless+headphones
```

## Auth & Authorization

```php
// Bearer token — always authenticate before business logic
Route::middleware('auth:api')->group(function () {
    Route::apiResource('products', ProductApiController::class);
});
```

### 401 vs 403
- `401 Unauthenticated` — no valid token / session expired
- `403 Forbidden` — valid identity but lacks permission

### IDOR / Ownership Check
```php
// ❌ Anyone can access any order
$order = Order::findOrFail($id);

// ✅ Ownership verification
$order = Order::where('id', $id)
    ->where('user_id', auth()->id())
    ->firstOrFail();
```

## Laravel JsonResource (Mandatory)

All API responses MUST use JsonResource. No manual array mapping in controllers.

```php
// app/Http/Resources/Api/ProductResource.php
class ProductResource extends JsonResource
{
    public function toArray($request): array
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'price' => $this->price,
            'category' => new CategoryResource($this->whenLoaded('category')),
            'tags' => TagResource::collection($this->whenLoaded('tags')),
            'is_featured' => $this->when($this->is_featured, true),
            'created_at' => $this->created_at->toIso8601String(),
        ];
    }
}
```

Rules:
- Path: `app/Http/Resources/Api/{Name}Resource.php`
- Use `when()` / `whenLoaded()` for conditional fields
- Dates: always `->toIso8601String()`
- No business logic in resources

## Laravel FormRequest

```php
class CreateProductRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // Permission handled by middleware
    }

    public function rules(): array
    {
        return [
            'name'  => ['required', 'string', 'max:255', 'unique:products'],
            'price' => ['required', 'numeric', 'min:0'],
        ];
    }

    // Required for Scribe documentation
    public function bodyParameters(): array
    {
        return [
            'name'  => ['description' => 'Product name', 'example' => 'iPhone 15'],
            'price' => ['description' => 'Price in VND', 'example' => 29990000],
        ];
    }
}
```

## Scribe API Documentation

```php
/**
 * @group Products
 *
 * APIs for managing products.
 */
class ProductApiController extends Controller
{
    /**
     * List products
     *
     * @queryParam limit int Limit per page. Example: 20
     * @queryParam page int Page number. Example: 1
     */
    public function index(Request $request) { /* ... */ }
}

// Unauthenticated endpoints
/**
 * @unauthenticated
 */
public function publicEndpoint() { /* ... */ }
```

Rules:
- Every controller: `@group`
- Public endpoints: `@unauthenticated`
- FormRequest: `bodyParameters()` method
- Run `php artisan scribe:generate` after changes

## Rate Limiting (Valkey-backed)

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

## Checklist

- [ ] URL follows `/api/v1/{resource}` (plural, kebab-case)
- [ ] Correct HTTP method and status codes
- [ ] Response follows `{ data, meta, errors }` format
- [ ] FormRequest with `rules()` for validation
- [ ] FormRequest with `bodyParameters()` for Scribe
- [ ] JsonResource for all responses (no manual mapping)
- [ ] `apiError()` for error responses — no stack trace leak
- [ ] Pagination via `apiPaginated()` — avoid `COUNT(*)` on large tables
- [ ] Auth middleware before business logic
- [ ] Authorization: IDOR ownership check where applicable
- [ ] Rate limiting configured
- [ ] Scribe: `@group` on controller, `@unauthenticated` where needed
- [ ] Run `php artisan scribe:generate` and verify

