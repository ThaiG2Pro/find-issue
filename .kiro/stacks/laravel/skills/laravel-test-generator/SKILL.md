---
name: laravel-test-generator
description: >
  Generate unit and feature tests cho Laravel services/controllers.
  Use when "generate tests", "create test cases", "add tests for", "test coverage".
tags: [testing, laravel]
---

# Test Generator — Laravel

Test generation patterns cho Laravel, align với `laravel-tdd-workflow` skill.

## When to Activate

- Viết tests cho service/controller mới (S4)
- Generate test scenarios từ AC trong requirements.md (S5)
- Tăng coverage lên ≥80%

## How to Use

```
Dùng skill test-generator cho: Modules/Product/Services/ProductService.php
Dùng skill test-generator để generate feature tests cho: Modules/Product/Http/Controllers/ProductController.php
```

## Process

1. Read source file → extract public methods
2. For each method → generate test cases from checklist
3. Unit test cho Service → mock Repository
4. Feature test cho Controller → real DB + actingAs

## Unit Test Generation (Service)

Read service → for each public method, generate:

```php
/** @test */
public function it_[expected_behavior]_when_[condition](): void
{
    // Arrange
    $this->repo->shouldReceive('method')->with($args)->andReturn($result);

    // Act
    $result = $this->service->methodUnderTest($input);

    // Assert
    $this->assertEquals($expected, $result);
}
```

### Cases per method:
- Happy path (valid input → expected output)
- Not found (→ ModelNotFoundException)
- Validation fail (→ ValidationException)
- Duplicate (→ QueryException unique violation)
- Side effects (Cache flush, Queue dispatch, Event fire)

## Feature Test Generation (Controller)

Read controller + routes → for each action, generate:

```php
/** @test */
public function user_can_[action]_[resource](): void
{
    // Arrange — factory data
    $model = Model::factory()->create();

    // Act — HTTP request
    $response = $this->actingAs($this->adminUser())
        ->get(route('adminweb.module.action'));

    // Assert
    $response->assertStatus(200);
}
```

### Cases per route:
| Route | Tests |
|-------|-------|
| GET index | 200 + view name + data passed |
| GET create | 200 + view name |
| POST store | Valid → redirect + assertDatabaseHas |
| POST store | Invalid → assertSessionHasErrors |
| GET edit | 200 + view + model data |
| PUT update | Valid → redirect + assertDatabaseHas |
| DELETE destroy | Redirect + assertSoftDeleted/assertDatabaseMissing |
| Any | Unauthenticated → redirect login |
| Any | Unauthorized → 403 |

## Mock Patterns

```php
// Repository mock
$this->repo = Mockery::mock(ProductRepository::class);
$this->app->instance(ProductRepository::class, $this->repo);

// Storage mock (S3 uploads)
Storage::fake('s3');
$file = UploadedFile::fake()->image('photo.jpg', 100, 100);

// Queue mock
Queue::fake();
// ... trigger action ...
Queue::assertPushed(ExportJob::class, function ($job) {
    return $job->userId === 1;
});

// HTTP mock (external APIs)
Http::fake(['api.example.com/*' => Http::response(['ok' => true])]);

// Cache mock
Cache::shouldReceive('tags')->with(['products'])->andReturnSelf();
Cache::shouldReceive('flush')->once();
```

## Test Cases Checklist

### From AC (requirements.md)
- [ ] Mỗi AC có ít nhất 1 test case
- [ ] Happy path — valid input, expected response
- [ ] Error path — invalid input, expected errors
- [ ] Edge cases — empty, null, boundary values

### Business Logic
- [ ] State transitions (PENDING → ACTIVE → INACTIVE)
- [ ] Side effects: queue, cache, event
- [ ] Idempotency

### Auth & Permission
- [ ] Unauthenticated → redirect login
- [ ] Wrong role → 403
- [ ] `admin.can` middleware enforced
