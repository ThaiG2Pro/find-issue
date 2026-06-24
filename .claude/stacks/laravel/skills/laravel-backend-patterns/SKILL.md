---
name: laravel-backend-patterns
description: >
  Backend patterns cho Laravel. Service layer, repository pattern,
  Eloquent best practices, Form Requests, error handling, caching.
tags: [backend, laravel]
---

# Backend Patterns — Laravel

## Module Structure (nwidart/laravel-modules)

```
Modules/{Domain}/
├── Config/
├── Database/
│   ├── Migrations/
│   └── Seeders/
├── Entities/ (Models)
├── Http/
│   ├── Controllers/
│   ├── Middleware/
│   └── Requests/
├── Providers/
├── Resources/
│   └── views/
├── Routes/
├── Services/
├── Repositories/
└── Tests/
```

## Layer Responsibilities

### Controller — Thin
```php
class ProductController extends Controller
{
    public function __construct(private ProductService $service) {}

    public function store(CreateProductRequest $request)
    {
        $product = $this->service->create($request->validated());
        return response()->json(['data' => $product, 'meta' => $this->meta($request)], 201);
    }
}
```

### Service — Business logic
```php
class ProductService
{
    public function __construct(private ProductRepository $repo) {}

    public function create(array $data): Product
    {
        return DB::transaction(function () use ($data) {
            $product = $this->repo->create($data);
            Cache::tags(['products'])->flush();
            return $product;
        });
    }
}
```

### Repository — DB access
```php
class ProductRepository
{
    public function __construct(private Product $model) {}

    public function findByStatus(string $status): Collection
    {
        return $this->model
            ->where('status', $status)
            ->whereNull('deleted_at')
            ->get();
    }
}
```

## Eloquent Best Practices

```php
// ❌ N+1
$orders = Order::all();
foreach ($orders as $order) {
    echo $order->items->count(); // N queries
}

// ✅ Eager load
$orders = Order::with('items')->get();

// ✅ Chunking for large datasets
Product::chunk(1000, function ($products) {
    foreach ($products as $product) { /* process */ }
});
```

## Validation — Form Requests

```php
class CreateProductRequest extends FormRequest
{
    public function authorize(): bool { return true; }

    public function rules(): array
    {
        return [
            'name' => ['required', 'string', 'max:255', 'unique:products'],
            'price' => ['required', 'numeric', 'min:0'],
            'description' => ['nullable', 'string'],
        ];
    }
}
```

## Error Handling

```php
// API response format
class ApiExceptionHandler
{
    public function render($request, Throwable $e)
    {
        return response()->json([
            'errors' => [['code' => $this->getCode($e), 'message' => $e->getMessage()]],
            'meta' => ['statusCode' => $this->getStatus($e), 'timestamp' => now()->toIso8601String()],
        ], $this->getStatus($e));
    }
}
```

## Checklist

- [ ] Controller thin — no business logic
- [ ] Service owns business logic
- [ ] Form Request for validation
- [ ] Eager loading (no N+1)
- [ ] DB::transaction for multi-table writes
- [ ] Cache with tags, flush on write
- [ ] Structured logging, no PII
