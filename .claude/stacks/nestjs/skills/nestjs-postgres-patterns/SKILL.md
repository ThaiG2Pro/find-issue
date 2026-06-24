---
name: nestjs-postgres-patterns
description: >
  PostgreSQL database patterns for query optimization, schema design, indexing,
  and security. Quick reference for common patterns, index types, data types,
  and anti-pattern detection. Based on Supabase best practices.
tags: [database, nestjs, postgresql]
---

# PostgreSQL Patterns

Quick reference cho Aurora PostgreSQL, align với `CLAUDE.md`.

## When to Activate

- Writing SQL queries or migrations (S3, S4)
- Designing database schemas
- Troubleshooting slow queries
- Reviewing query performance (S5)

## Index Cheat Sheet

| Query Pattern | Index Type | Example |
|--------------|------------|---------|
| `WHERE col = value` | B-tree | `CREATE INDEX idx ON t (col)` |
| `WHERE col > value` | B-tree | `CREATE INDEX idx ON t (col)` |
| `WHERE a = x AND b > y` | Composite | `CREATE INDEX idx ON t (a, b)` |
| `WHERE jsonb @> '{}'` | GIN | `CREATE INDEX idx ON t USING gin (col)` |
| Full-text search | GIN | `CREATE INDEX idx ON t USING gin (col)` |
| Time-series ranges | BRIN | `CREATE INDEX idx ON t USING brin (col)` |

## Naming (P1)

```sql
-- Tables: snake_case
CREATE TABLE supplier_variants (...);

-- Indexes: idx_{table}_{column(s)}
CREATE INDEX idx_users_email ON users(email);

-- Foreign Keys: fk_{table}_{ref_table}
ALTER TABLE orders ADD CONSTRAINT fk_orders_users FOREIGN KEY (user_id) REFERENCES users(id);
```

## Data Types

| Use Case | Correct Type | Avoid |
|----------|-------------|-------|
| IDs | `UUID` | `int`, `bigint` |
| Strings | `TEXT` or `VARCHAR(n)` | `CHAR` |
| Timestamps | `TIMESTAMPTZ` | `TIMESTAMP` (no timezone) |
| Money/Price | `NUMERIC(10,2)` | `FLOAT`, `DOUBLE` |
| Flags | `BOOLEAN` | `VARCHAR`, `INT` |
| Status | `VARCHAR` + CHECK | Magic numbers |

## Common Patterns

### Composite Index (equality first, then range)
```sql
CREATE INDEX idx_orders_status_created ON orders (status, created_at);
-- Works for: WHERE status = 'PENDING' AND created_at > '2026-01-01'
```

### Partial Index (smaller, faster)
```sql
CREATE INDEX idx_users_active_email ON users (email) WHERE deleted_at IS NULL;
```

### Covering Index (avoid table lookup)
```sql
CREATE INDEX idx_users_email_cover ON users (email) INCLUDE (name, created_at);
```

### Cursor Pagination (O(1) vs OFFSET O(n))
```sql
SELECT * FROM products WHERE id > $last_id ORDER BY id LIMIT 20;
```

### Queue Processing (skip locked)
```sql
UPDATE jobs SET status = 'processing'
WHERE id = (
  SELECT id FROM jobs WHERE status = 'pending'
  ORDER BY created_at LIMIT 1
  FOR UPDATE SKIP LOCKED
) RETURNING *;
```

### UPSERT
```sql
INSERT INTO settings (user_id, key, value)
VALUES ($1, $2, $3)
ON CONFLICT (user_id, key)
DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
```

## Anti-Pattern Detection

```sql
-- Find unindexed foreign keys
SELECT conrelid::regclass, a.attname
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.contype = 'f'
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = c.conrelid AND a.attnum = ANY(i.indkey)
  );

-- Find slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC;

-- Check table bloat
SELECT relname, n_dead_tup, last_vacuum
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC;
```
