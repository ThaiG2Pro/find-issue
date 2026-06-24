---
name: laravel-database-migrations
description: >
  Database migration patterns cho Laravel + Eloquent.
  Safe schema changes, zero-downtime, rollback.
tags: [database, laravel]
---

# Database Migrations — Laravel

## Core Rules

1. Every change is a migration — never alter DB manually
2. Migrations are immutable once deployed
3. Schema and data migrations are separate
4. Migration must have rollback (`up()` and `down()`)

## File Format

```bash
# Generate migration
php artisan make:migration create_products_table
php artisan make:migration add_avatar_to_users_table

# Run / Rollback
php artisan migrate
php artisan migrate:rollback
php artisan migrate:status
```

## Safe Patterns

### Adding Column
```php
// ✅ Nullable — safe
Schema::table('users', function (Blueprint $table) {
    $table->string('avatar_url')->nullable();
});

// ✅ With default — safe
Schema::table('users', function (Blueprint $table) {
    $table->boolean('is_active')->default(true);
});

// ❌ NOT NULL without default — locks table
$table->string('role');
```

### Adding Index
```php
// Standard (OK for small tables)
$table->index('email');

// For large tables — use raw SQL
DB::statement('CREATE INDEX CONCURRENTLY idx_users_email ON users (email)');
```

### Rollback
```php
public function down(): void
{
    Schema::table('users', function (Blueprint $table) {
        $table->dropColumn('avatar_url');
    });
}
```

## Base Fields (SoftDeletes)

```php
Schema::create('products', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->string('name');
    $table->timestamps();      // created_at, updated_at
    $table->softDeletes();     // deleted_at
});
```

## Naming Conventions

- Tables: `snake_case`, plural (`order_items`)
- Columns: `snake_case` (`user_id`, `created_at`)
- Indexes: `idx_{table}_{columns}`
- Foreign keys: Laravel auto-names, or `fk_{table}_{ref}`

## Checklist

- [ ] Has both up() and down()
- [ ] New columns nullable or have defaults
- [ ] Indexes on frequently queried columns
- [ ] Tested rollback locally
- [ ] Schema and data migrations separate
