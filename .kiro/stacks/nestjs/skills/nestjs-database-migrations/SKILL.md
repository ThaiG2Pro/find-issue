---
name: nestjs-database-migrations
description: >
  Database migration patterns cho TypeORM + Aurora PostgreSQL.
  Safe schema changes, zero-downtime, rollback, batch data migrations.
tags: [database, nestjs]
---

# Database Migrations

TypeORM migration patterns cho Aurora PostgreSQL, align với `CLAUDE.md`.

## When to Activate

- Creating or altering tables (S3 design, S4 build)
- Running data migrations
- Planning zero-downtime schema changes
- Reviewing migration PRs (S5)

## Core Rules (P1)

1. **Every change is a migration** — never alter production DB manually
2. **Migrations are immutable once deployed** — never edit deployed migrations
3. **Schema and data migrations are separate** — never mix DDL and DML
4. **Migration must have rollback** — `up()` and `down()` methods
5. **File format**: TypeORM TypeScript class `{timestamp}-{PascalCaseDescription}.ts` in `apps/api/src/migrations/`

## Safety Checklist

- [ ] Has both UP and DOWN (or marked irreversible)
- [ ] No full table locks on large tables
- [ ] New columns are nullable or have defaults
- [ ] Indexes created CONCURRENTLY
- [ ] Data backfill is separate migration
- [ ] Tested against production-sized data
- [ ] Rollback plan documented

## PostgreSQL Patterns

### Adding Column Safely
```sql
-- ✅ Nullable — no lock
ALTER TABLE users ADD COLUMN avatar_url TEXT;

-- ✅ With default (PG 11+ instant, no rewrite)
ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;

-- ❌ NOT NULL without default — locks table, rewrites all rows
ALTER TABLE users ADD COLUMN role TEXT NOT NULL;
```

### Adding Index Without Downtime
```sql
-- ❌ Blocks writes on large tables
CREATE INDEX idx_users_email ON users (email);

-- ✅ Non-blocking
CREATE INDEX CONCURRENTLY idx_users_email ON users (email);
```

### Renaming Column (Zero-Downtime)
```sql
-- Step 1: Add new column
ALTER TABLE users ADD COLUMN display_name TEXT;

-- Step 2: Backfill (separate migration)
UPDATE users SET display_name = username WHERE display_name IS NULL;

-- Step 3: Deploy app reading/writing both columns
-- Step 4: Drop old column (separate migration, after deploy)
ALTER TABLE users DROP COLUMN username;
```

### Large Data Migration (Batch)
```sql
DO $$
DECLARE
  batch_size INT := 10000;
  rows_updated INT;
BEGIN
  LOOP
    UPDATE users
    SET normalized_email = LOWER(email)
    WHERE id IN (
      SELECT id FROM users
      WHERE normalized_email IS NULL
      LIMIT batch_size
      FOR UPDATE SKIP LOCKED
    );
    GET DIAGNOSTICS rows_updated = ROW_COUNT;
    EXIT WHEN rows_updated = 0;
    COMMIT;
  END LOOP;
END $$;
```

## TypeORM Migration

```bash
# Generate migration from entity changes
npm run typeorm migration:generate -- -n AddUserAvatar

# Create empty migration for custom SQL
npm run typeorm migration:create -- -n BackfillDisplayNames

# Run migrations
npm run typeorm migration:run

# Revert last migration
npm run typeorm migration:revert
```

### Migration File
```typescript
export class AddUserAvatar1711800000000 implements MigrationInterface {
  async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`ALTER TABLE users ADD COLUMN avatar_url TEXT`);
    await queryRunner.query(
      `CREATE INDEX CONCURRENTLY idx_users_avatar ON users (avatar_url) WHERE avatar_url IS NOT NULL`
    );
  }

  async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS idx_users_avatar`);
    await queryRunner.query(`ALTER TABLE users DROP COLUMN IF EXISTS avatar_url`);
  }
}
```

## Naming Conventions (P1)

```sql
-- Tables: snake_case
CREATE TABLE order_items (...);

-- Indexes: idx_{table}_{column(s)}
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_orders_status_created_at ON orders(status, created_at);

-- Foreign Keys: fk_{table}_{ref_table}
ALTER TABLE orders ADD CONSTRAINT fk_orders_users FOREIGN KEY (user_id) REFERENCES users(id);
```

## Zero-Downtime Strategy

```
Phase 1: EXPAND — Add new column (nullable/default), deploy app writing both
Phase 2: MIGRATE — Backfill data, deploy app reading from new
Phase 3: CONTRACT — Drop old column in separate migration
```

## Anti-Patterns

| Anti-Pattern | Better Approach |
|-------------|-----------------|
| Manual SQL in production | Always use migration files |
| Editing deployed migrations | Create new migration |
| NOT NULL without default | Add nullable, backfill, then constraint |
| Inline index on large table | CREATE INDEX CONCURRENTLY |
| Schema + data in one migration | Separate migrations |
| Drop column before removing code | Remove code first, drop next deploy |
