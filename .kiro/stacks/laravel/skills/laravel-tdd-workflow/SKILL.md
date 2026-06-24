---
name: laravel-tdd-workflow
description: >
  TDD workflow cho Laravel + PHPUnit. Unit tests (mock deps) + Feature tests
  (SQLite in-memory mặc định; RefreshDatabase + real DB chỉ khi chỉ định; multi-DB mock service).
  Use when "TDD", "test driven", "write tests first", "red green refactor".
tags: [testing, laravel]
---

# TDD Workflow — Laravel

PHPUnit test patterns cho Laravel, align với company conventions.

## When to Activate

- Writing new features (S4 Build)
- Fixing bugs
- Refactoring code
- QA validation (S5)

## Coverage Requirements (P1)

- Minimum: **80%** for lines, branches
- Hard fail in CI if below threshold
- Exclude: config, routes, migrations, views, vendor

## Test Types

| Type | DB Strategy | Location | Focus |
|------|-------------|----------|-------|
| Unit | Mock repository/service | `tests/Unit/` | Business logic in isolation |
| Feature — Single-DB | **SQLite in-memory** (default) | `tests/Feature/` | HTTP endpoints, DB operations |
| Feature — Single-DB | RefreshDatabase + real test DB (manual) | `tests/Feature/` | Khi cần JSON/spatial/stored proc |
| Feature — Multi-DB | Mock tầng Service | `tests/Feature/` | HTTP/middleware, không chạm DB |

**Cách xác định strategy cho Feature tests:**
1. Đọc `config/database.php` — đếm số connections khác nhau
2. **1 connection (single-DB)** → SQLite in-memory mặc định
3. **≥2 connections (multi-DB)** → mock tầng Service
4. **Single-DB nhưng dùng JSON/spatial columns hoặc stored procedures** → RefreshDatabase + real test DB (chỉ định tường minh)

## TDD Loop

1. **Write test** (from AC in requirements.md)
2. **Run test** → should FAIL: `php artisan test --filter=TestName`
3. **Write minimal code** to make test pass
4. **Run test** → should PASS
5. **Refactor** while keeping tests green
6. **Check coverage** → must be ≥80%

## Unit Test Template

```php
<?php

namespace Modules\Product\Tests\Unit;

use Mockery;
use Tests\TestCase;
use Modules\Product\Services\ProductService;
use Modules\Product\Repositories\ProductRepository;
use Illuminate\Database\Eloquent\ModelNotFoundException;

class ProductServiceTest extends TestCase
{
    private ProductService $service;
    private $repo;

    protected function setUp(): void
    {
        parent::setUp();
        $this->repo = Mockery::mock(ProductRepository::class);
        $this->service = new ProductService($this->repo);
    }

    /** @test */
    public function it_returns_product_when_found(): void
    {
        $product = (object) ['id' => 1, 'name' => 'iPhone 15'];
        $this->repo->shouldReceive('findOrFail')->with(1)->andReturn($product);

        $result = $this->service->findById(1);

        $this->assertEquals('iPhone 15', $result->name);
    }

    /** @test */
    public function it_throws_when_product_not_found(): void
    {
        $this->repo->shouldReceive('findOrFail')->with(999)
            ->andThrow(new ModelNotFoundException());

        $this->expectException(ModelNotFoundException::class);
        $this->service->findById(999);
    }

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }
}
```

## Feature Test Template — Single-DB (SQLite in-memory, default)

Enable SQLite in-memory trong `phpunit.xml`:

```xml
<php>
    <env name="APP_ENV" value="testing"/>
    <env name="DB_CONNECTION" value="sqlite"/>
    <env name="DB_DATABASE" value=":memory:"/>
    <env name="CACHE_STORE" value="array"/>
    <env name="QUEUE_CONNECTION" value="sync"/>
</php>
```

```php
<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use App\Models\Product;
use Tests\TestCase;

class ProductControllerTest extends TestCase
{
    use RefreshDatabase; // SQLite :memory: — mỗi test reset tự động

    /** @test */
    public function user_can_create_product_with_valid_data(): void
    {
        $data = ['name' => 'New Product', 'price' => 100000];

        $response = $this->actingAs($this->adminUser())
            ->postJson('/api/products', $data);

        $response->assertStatus(201);
        $this->assertDatabaseHas('products', ['name' => 'New Product']);
    }

    /** @test */
    public function store_fails_with_invalid_data(): void
    {
        $response = $this->actingAs($this->adminUser())
            ->postJson('/api/products', []);

        $response->assertStatus(422)->assertJsonValidationErrors(['name', 'price']);
    }

    /** @test */
    public function unauthenticated_request_returns_401(): void
    {
        $this->postJson('/api/products', [])->assertStatus(401);
    }
}
```

## Feature Test Template — Single-DB (RefreshDatabase + real test DB, manual)

Dùng khi: JSON columns, spatial types, stored procedures, full-text search — thứ SQLite không hỗ trợ.

Cấu hình `phpunit.xml` (KHÔNG set sqlite):
```xml
<php>
    <env name="APP_ENV" value="testing"/>
    <env name="DB_CONNECTION" value="mysql"/>
    <env name="DB_DATABASE" value="myapp_test"/>  <!-- DB test riêng, KHÔNG dùng production -->
    <env name="CACHE_STORE" value="array"/>
    <env name="QUEUE_CONNECTION" value="sync"/>
</php>
```

```php
class ProductControllerTest extends TestCase
{
    use RefreshDatabase; // real MySQL test DB — chạy migration trước mỗi test suite
    // ...
}
```

> ⚠️ Phải tạo DB test riêng và chạy migration trước: `php artisan migrate --env=testing`

## Feature Test Template — Multi-DB (mock tầng Service)

Dùng khi project có ≥2 DB connections (host khác nhau) — `RefreshDatabase` không reset được tất cả connections.

```php
<?php

namespace Tests\Feature\Http;

use App\Services\OrderService;
use Tests\TestCase;

/**
 * Feature test for OrderController.
 * DB/Redis isolated via OrderService mock — multi-DB project.
 */
class OrderControllerTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();

        // Disable unrelated middleware
        $this->withoutMiddleware([ThrottleRequests::class]);

        // Mock service layer — không chạm DB hay Redis
        $this->mock(OrderService::class, fn ($m) => $m
            ->shouldReceive('findById')->with(1)->andReturn(
                (object) ['id' => 1, 'status' => 'pending']
            )
            ->shouldReceive('cancel')->andReturn(true)
        );
    }

    public function test_get_order_returns_200(): void
    {
        $this->getJson('/api/orders/1')->assertStatus(200)
            ->assertJsonFragment(['status' => 'pending']);
    }

    public function test_cancel_order_returns_200(): void
    {
        $this->postJson('/api/orders/1/cancel')->assertStatus(200);
    }
}
```

> ⚠️ Mock tầng Service, KHÔNG mock Repository trực tiếp trong Feature test —
> mất đi giá trị kiểm tra HTTP contract và middleware behavior.

## Mock Patterns

```php
// Mock Storage (S3)
Storage::fake('s3');

// Mock Queue
Queue::fake();
// ... action ...
Queue::assertPushed(ExportJob::class);

// Mock Cache
Cache::shouldReceive('tags->flush')->once();

// Mock External API
Http::fake([
    'api.external.com/*' => Http::response(['data' => 'ok'], 200),
]);
```

## Test Cases Checklist

- [ ] Happy path — valid input, expected redirect/response
- [ ] Validation errors — missing/invalid fields, `assertSessionHasErrors`
- [ ] Auth — unauthenticated redirect, forbidden (403)
- [ ] Permission — `admin.can` middleware tested
- [ ] Edge cases — empty, null, boundary values
- [ ] Business rules — state transitions, calculations
- [ ] Side effects — queue dispatched, cache flushed, event fired

## Commands

```bash
php artisan test                              # All tests
php artisan test --filter=ProductServiceTest  # Specific test
php artisan test --testsuite=Modules          # Module tests only
php artisan test --coverage                   # With coverage
php artisan test --parallel                   # Parallel execution
```

## CI/CD Test Flow

```bash
./vendor/bin/phpstan analyse app tests --memory-limit=512M  # 1. Static analysis
php artisan test --testsuite=Unit                            # 2. Unit tests
php artisan test --testsuite=Feature                         # 3. Feature tests
php artisan test --coverage                                  # 4. Coverage check
```

## Rules

- ✅ Unit tests: Mock repositories, external services, queues
- ✅ Feature tests — Single-DB: SQLite in-memory mặc định (`DB_CONNECTION=sqlite`, `DB_DATABASE=:memory:`)
- ✅ Feature tests — Single-DB: RefreshDatabase + real test DB chỉ khi chỉ định tường minh (JSON/spatial/stored proc)
- ✅ Feature tests — Multi-DB (≥2 connections): mock tầng Service, KHÔNG mock Repository
- ❌ KHÔNG dùng production DB hay staging DB để chạy test
- ❌ KHÔNG để Feature test multi-DB không có assertion thực chất (chỉ assertStatus 200 không đủ)
- ✅ Use `/** @test */` annotation hoặc `test_` prefix
- ✅ Descriptive names: `it_throws_when_product_not_found`
- ✅ AAA pattern: Arrange → Act → Assert
- ✅ Factory cho test data — không hardcode
