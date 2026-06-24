# API & Code Conventions

> Seeded by the `nestjs` stack preset. Adjust to your project's real contract.

## API Response Format
- Success: `{ "data": {}, "meta": { "timestamp", "path", "method" } }`
- Error: `{ "errors": [{ "code", "message", "field" }], "meta": { ..., "statusCode" } }`

## HTTP Status Policy
- Business + validation errors use real 4xx/5xx codes (NOT 200-with-error-body).
- 200 OK / 201 Created / 204 No Content / 400 / 401 / 403 / 404 / 409 / 422 / 429 / 500.

## URL / Resource Naming
- Plural nouns, kebab-case, max 2 nesting levels, versioned (`/v1/`).
- Host already prefixes `/api`; controllers declare the path after it.

## Naming Conventions
- Files `kebab-case.ts`; classes `PascalCase`; interfaces `I`-prefix; types `PascalCase`;
  functions/vars `camelCase`; constants `UPPER_SNAKE_CASE`; DB tables/columns `snake_case`.

## Validation
- Validate every request body with Zod or class-validator at the boundary (DTO/Pipe).
- Reject unknown fields (whitelist + forbidNonWhitelisted), enforce `Content-Type: application/json`.

## Documentation
- OpenAPI mandatory: `@ApiTags`/`@ApiOperation`/`@ApiResponse` on controllers, `@ApiProperty` on DTOs.
